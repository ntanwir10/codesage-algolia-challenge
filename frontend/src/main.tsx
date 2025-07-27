/**
 * CodeSage - MCP-First Code Discovery: Frontend Entry Point
 *
 * This is the entry point for the CodeSage frontend - the only code discovery
 * tool built entirely around the Model Context Protocol (MCP) for seamless
 * AI integration with Claude Desktop and other MCP clients.
 *
 * The frontend provides repository management while AI interactions happen
 * through MCP integration.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
