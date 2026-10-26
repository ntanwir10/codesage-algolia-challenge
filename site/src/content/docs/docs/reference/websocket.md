---
title: WebSocket reference
description: The /ws endpoint that pushes live repository status, with authentication, connection caps, close codes, every frame type and a JavaScript client.
---

The backend pushes indexing progress over a WebSocket at `/ws`. The dashboard uses it to update progress bars without waiting for its 3-second poll. You can use it from any WebSocket client. For the REST side of the same data, see [REST API](/docs/reference/rest-api/#get-apiv1repositoriesrepository_idstatus).

The endpoint is `ws://127.0.0.1:8001/ws` for a local install. Behind the production nginx it is `wss://<your-host>/ws`. Source: [`websocket_service.py`](https://github.com/ntanwir10/codesage-algolia-challenge/blob/master/backend/app/services/websocket_service.py).

## Connecting

Two checks run before your code talks to the endpoint: the request guard, then the key check.

### Request guard

The same guard that protects HTTP also covers the handshake. It refuses the handshake when:

- the `Host` header is not allowed (see [Error shapes](/docs/reference/rest-api/#error-shapes) for the rules);
- no key is configured and the TCP peer is not a loopback address;
- an `Origin` header is present and is neither in `CORS_ORIGINS` nor the API's own origin. A client that sends no `Origin`, such as Node or `websocat`, passes.

The guard sends a close with code `1008` before the handshake completes. Because the close comes before `accept`, a browser reports it as an abnormal close (`1006`) rather than `1008`. Check the backend log if a browser connection fails with `1006` and the key is correct.

### Authentication

When `CODESAGE_API_KEY` is set, the endpoint needs the key. It reads it from either place:

| Where | Used by | Format |
| --- | --- | --- |
| Subprotocol | Browsers, which cannot set headers on a WebSocket | `codesage.key.<hex>`, where `<hex>` is the UTF-8 bytes of the key written in hexadecimal |
| `X-API-Key` header | Servers, scripts and the production nginx | The key as plain text |

The subprotocol is checked first. A subprotocol with bad hexadecimal or invalid UTF-8 counts as no key. The key never appears in the URL, so access logs do not record it.

With no key configured, any connection passes this check.

### Subprotocol echo

Always offer `codesage` as well as the key subprotocol. The server echoes `codesage` when you offered it, and echoes nothing otherwise. A browser closes a connection when it offered protocols and the server selected none, so a client that offers only `codesage.key.<hex>` fails.

```js title="Offered subprotocols"
["codesage", "codesage.key.6d792d6b6579"]
```

### Connection caps

| Cap | Value |
| --- | --- |
| Open connections, all clients | 200 |
| Open connections per client address | 20 |

The client address is the TCP peer. Behind the production nginx, uvicorn takes it from `X-Forwarded-For`. A new connection past either cap is accepted and then closed, so the client sees the close code.

### Close codes

| Code | Reason text | Cause | Should you retry? |
| --- | --- | --- | --- |
| `1008` | `Invalid or missing API key` | A key is configured and the connection has none or a wrong one | No. Fix the key |
| `1013` | `Too many connections; try again later` | A connection cap was reached | Yes, with backoff |
| `1011` | `Internal error` | An unexpected exception in the handler | Yes, with backoff |
| `1000` | | Normal close, sent by clients when they shut down | |

The server accepts before it closes with `1008` or `1013`, because a close before accept reaches browsers as `1006`, which says nothing about why. The dashboard treats `1008` as an authentication failure and stops retrying.

## Client frames

Send text frames containing one JSON object each. The `type` must be one of three values.

| Type | Fields | Reply |
| --- | --- | --- |
| `subscribe` | `repository_id`: positive integer | `subscribed`, or `error` |
| `unsubscribe` | `repository_id`: positive integer | `unsubscribed` |
| `ping` | none | `pong` |

```json title="subscribe"
{"type": "subscribe", "repository_id": 7}
```

```json title="unsubscribe"
{"type": "unsubscribe", "repository_id": 7}
```

```json title="ping"
{"type": "ping"}
```

`repository_id` must be an integer greater than zero. A boolean, a float, a string or `0` is refused. The server does not check that the repository exists, so you can subscribe before it is created. Subscribing twice to the same repository is harmless and counts once.

A connection can hold at most 100 subscriptions. A subscribe past the cap gets an `error` frame, and the connection stays open.

A bad frame never closes the connection. It gets an `error` frame and the loop goes on.

## Server frames

Every frame is `{"type": ..., "data": {...}}`. `pong` has no `data`.

### `connected`

Sent once, right after the connection is accepted. Treat the connection as ready only after you see it.

```json
{
  "type": "connected",
  "data": {
    "message": "Connected to CodeSage real-time updates",
    "timestamp": "2026-10-26T14:00:00.123456+00:00"
  }
}
```

### `subscribed` and `unsubscribed`

```json
{"type": "subscribed", "data": {"repository_id": 7}}
```

```json
{"type": "unsubscribed", "data": {"repository_id": 7}}
```

`unsubscribed` is sent even if you were not subscribed.

### `pong`

```json
{"type": "pong"}
```

### `error`

| `data.message` | Cause |
| --- | --- |
| `Invalid JSON` | The frame is not valid JSON |
| `Message must be a JSON object` | The JSON is an array, string, number or `null` |
| `Unknown message type` | `type` is missing, not a string, or not one of the three client types |
| `repository_id must be a positive integer` | `subscribe` or `unsubscribe` without a valid `repository_id` |
| `At most 100 subscriptions per connection` | A `subscribe` would be the 101st |

```json
{"type": "error", "data": {"message": "Unknown message type"}}
```

### `repository_status`

Sent to every connection subscribed to that repository.

| Field | Type | Always present | Meaning |
| --- | --- | --- | --- |
| `repository_id` | integer | Yes | The repository |
| `status` | string | Yes | `processing`, `completed` or `failed` |
| `name` | string or null | Yes | Repository name |
| `processed_files` | integer | Yes | Files stored so far |
| `total_files` | integer | Yes | Files selected for the run |
| `timestamp` | string | Yes | ISO 8601 UTC time the frame was built |
| `message` | string | No | Present on the final frame |
| `error` | string | No | Present only when the run failed. Up to 500 characters |

A `pending` status is never broadcast. The first frame of a run is `processing`.

```json title="Run started"
{
  "type": "repository_status",
  "data": {
    "repository_id": 7,
    "status": "processing",
    "name": "octo/demo",
    "processed_files": 0,
    "total_files": 0,
    "timestamp": "2026-10-26T14:00:03.114201+00:00"
  }
}
```

```json title="After a batch of 200 files"
{
  "type": "repository_status",
  "data": {
    "repository_id": 7,
    "status": "processing",
    "name": "octo/demo",
    "processed_files": 200,
    "total_files": 214,
    "timestamp": "2026-10-26T14:00:19.552870+00:00"
  }
}
```

```json title="Completed"
{
  "type": "repository_status",
  "data": {
    "repository_id": 7,
    "status": "completed",
    "name": "octo/demo",
    "processed_files": 214,
    "total_files": 214,
    "timestamp": "2026-10-26T14:00:31.907316+00:00",
    "message": "Processing completed successfully"
  }
}
```

When a run completes but left something out, `message` carries the `Partially indexed: ...` text instead.

```json title="Failed"
{
  "type": "repository_status",
  "data": {
    "repository_id": 7,
    "status": "failed",
    "name": "octo/demo",
    "processed_files": 0,
    "total_files": 0,
    "timestamp": "2026-10-26T14:00:08.230044+00:00",
    "message": "Processing failed",
    "error": "No supported code files found in repository"
  }
}
```

### Broadcast timing

A frame goes out:

1. When a run starts. The status is already `processing`, even if the run is still waiting for one of the two run slots.
2. After each batch of 200 files is stored, with the new `processed_files`.
3. When the run ends, as `completed` or `failed`.

`total_files` is `0` until the first batch is stored, because the file count is only known after the repository is fetched. Deleting a repository sends no frame; it drops that repository's subscribers.

A frame is only built if at least one connection is subscribed. Nothing replays missed frames, so after a reconnect, subscribe again and read `/status` once to catch up.

## Send timeout and slow clients

Each send to a client has a 5-second timeout. A client that fails or stalls is removed and its socket is closed. Sends to all subscribers run at the same time, so several stalled clients cost one timeout, not one each. A processing run is never delayed by a client that stopped reading.

The server sends no pings of its own and has no application-level idle timeout. The production nginx closes idle `/ws` connections after an hour, so send a `ping` at least that often. The dashboard pings every 25 seconds.

## JavaScript client

This client runs in Node 22 or later, which has a global `WebSocket`. In a browser, replace the two `process.env` lines with constants. It follows [`frontend/src/services/websocket.ts`](https://github.com/ntanwir10/codesage-algolia-challenge/blob/master/frontend/src/services/websocket.ts): it offers both subprotocols, waits for `connected` before subscribing, pings every 25 seconds, treats `1008` as fatal and reconnects with jittered exponential backoff otherwise.

```js title="codesage-watch.mjs"
const URL = process.env.CODESAGE_WS_URL ?? "ws://127.0.0.1:8001/ws";
const KEY = process.env.CODESAGE_API_KEY ?? "";
const REPOSITORY_IDS = [7];

const HEARTBEAT_MS = 25_000;
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;

// The key is sent as hex in a subprotocol so it never appears in a URL or a log.
function protocols() {
  if (!KEY) return ["codesage"];
  const hex = Array.from(new TextEncoder().encode(KEY), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
  return ["codesage", `codesage.key.${hex}`];
}

let attempts = 0;

function connect() {
  const socket = new WebSocket(URL, protocols());
  let heartbeat = null;
  let awaitingPong = false;

  socket.onmessage = (event) => {
    awaitingPong = false; // any frame proves the connection is alive
    const frame = JSON.parse(String(event.data));

    switch (frame.type) {
      case "connected":
        attempts = 0;
        for (const id of REPOSITORY_IDS) {
          socket.send(JSON.stringify({ type: "subscribe", repository_id: id }));
        }
        heartbeat = setInterval(() => {
          if (awaitingPong) return socket.close(4000, "heartbeat timeout");
          awaitingPong = true;
          socket.send(JSON.stringify({ type: "ping" }));
        }, HEARTBEAT_MS);
        break;

      case "repository_status": {
        const u = frame.data;
        console.log(`${u.name} ${u.status} ${u.processed_files}/${u.total_files}`);
        if (u.error) console.error(`  failed: ${u.error}`);
        else if (u.message) console.log(`  ${u.message}`);
        break;
      }

      case "error":
        console.warn("server error:", frame.data?.message);
        break;

      default: // subscribed, unsubscribed, pong
        break;
    }
  };

  socket.onclose = (event) => {
    clearInterval(heartbeat);
    if (event.code === 1008) {
      console.error("Key rejected (1008). Check CODESAGE_API_KEY.");
      return; // retrying cannot help
    }
    const delay = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempts++);
    setTimeout(connect, Math.round(delay * (0.5 + Math.random() * 0.5)));
  };
}

connect();
```

Run it with `CODESAGE_API_KEY=... node codesage-watch.mjs`. Add a repository in another terminal and you see the frames arrive.

:::tip
For a quick look from a shell, `websocat` can send the key as a header instead: `websocat -H "X-API-Key: $CODESAGE_API_KEY" ws://127.0.0.1:8001/ws`. Type the JSON frames above and press Enter. See the [REST API guide](/docs/guides/rest-api/) for a full session.
:::

## Related pages

- [Web dashboard](/docs/guides/web-dashboard/) shows where progress appears.
- [Architecture](/docs/concepts/architecture/) shows how the run broadcasts status.
- [Security](/docs/concepts/security/) explains the key, host and origin checks.
