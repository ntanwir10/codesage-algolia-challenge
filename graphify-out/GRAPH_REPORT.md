# Graph Report - codesage-algolia-challenge  (2026-10-25)

## Corpus Check
- 114 files · ~50,145 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 16 file(s) not represented in the graph (top: (none) 7, .example 2, .ini 2)

## Summary
- 1563 nodes · 3293 edges · 71 communities (55 shown, 16 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 206 edges (avg confidence: 0.9)
- Token cost: 148,153 input · 0 output

## Community Hubs (Navigation)
- Code Entity Model
- GitHub API Client
- MCP Stdio Server
- WebSocket Live Updates
- Performance Monitoring
- Frontend API Errors
- Prod Docker Compose
- Claude Desktop Installer
- Dashboard UI Components
- Frontend WebSocket Client
- Repository Ingestion Service
- Code Parser Tests
- Alembic Migration Scripts
- Algolia Indexing
- Dev Docker Compose
- App Shell & UI Tests
- Tree-sitter Code Parser
- CI Workflow
- Algolia Test Fixtures
- Repository REST Endpoints
- Browser Request Security Tests
- API Security Guard
- Repository Job Errors
- TS App Config
- Database Migration Runner
- Settings & Config Validation
- Frontend Runtime Deps
- MCP Tools HTTP API
- Alembic Env & Settings
- CodeSage MCP Bridge
- TS Node Config
- Async Job Recovery
- Architecture & Data Model
- Processing Pipeline Tests
- shadcn Components Config
- Frontend Dev Deps
- Performance API Endpoints
- Repository Schemas
- Algolia Service Tests
- GitHub URL Form
- Python AST Extraction
- MCP Integration Docs
- MCP API Tests
- Product Overview & MCP Tools
- Backend Dependencies
- Frontend Package Meta
- Code File Model & Failures
- Fake Algolia Index
- ESLint Setup
- Layout & Connection Status
- Parsed Entity Extraction
- Proxy & Key Test Fixtures
- Status Polling Fallback
- Security Model Docs
- Docker Deployment Docs
- Production Auth & TLS
- Frontend Entry & Stack
- Repository Job Endpoint Tests
- Request ID & Error Handling
- API Key Tests
- Health Check
- Vite Build Config
- NPM Scripts
- Algolia Client Init
- Interrupted Job Recovery
- Tailwind Config
- Favicon Brand Icon
- Vite Env Types
- Root TS Config

## God Nodes (most connected - your core abstractions)
1. `Repository` - 51 edges
2. `RepositoryService` - 47 edges
3. `CodeParser` - 42 edges
4. `AlgoliaService` - 37 edges
5. `parse()` - 30 edges
6. `get_settings()` - 26 edges
7. `call_tool()` - 26 edges
8. `Backend` - 25 edges
9. `make_repository()` - 25 edges
10. `websocketService` - 25 edges

## Surprising Connections (you probably didn't know these)
- `stdio MCP bridge` --semantically_similar_to--> `stdio MCP Server (codesage_mcp)`  [INFERRED] [semantically similar]
  docs/MCP_INTEGRATION_GUIDE.md → README.md
- `Ingestion pipeline` --semantically_similar_to--> `Background Indexing Job`  [INFERRED] [semantically similar]
  docs/architecture.md → README.md
- `Real-time updates (/ws)` --semantically_similar_to--> `/ws WebSocket endpoint`  [INFERRED] [semantically similar]
  docs/architecture.md → README.md
- `find_patterns tool` --semantically_similar_to--> `find_patterns tool`  [INFERRED] [semantically similar]
  docs/MCP_INTEGRATION_GUIDE.md → README.md
- `One backend worker` --semantically_similar_to--> `Single worker constraint`  [INFERRED] [semantically similar]
  deployment/DOCKER.md → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **MCP tool call flow: Claude Desktop -> launcher -> bridge -> backend** — readme_claude_desktop, mcp_launcher, docs_mcp_integration_guide_stdio_bridge, docs_mcp_integration_guide_tools_call_endpoint, readme_fastapi_backend [EXTRACTED 1.00]
- **Ingestion: GitHub fetch, parse, SQLite store, Algolia index** — docs_architecture_ingestion_pipeline, readme_github_rest_api, readme_tree_sitter, docs_architecture_code_entities_table, readme_algolia [EXTRACTED 1.00]
- **API key protection mechanisms** — readme_codesage_api_key, readme_x_api_key_header, readme_websocket_subprotocol_auth, deployment_docker_nginx_basic_auth, docs_architecture_browser_request_guard, docs_architecture_constant_time_key_check [INFERRED 0.85]

## Communities (71 total, 16 thin omitted)

### Community 0 - "Code Entity Model"
Cohesion: 0.05
Nodes (60): CodeEntity, quote_path(), analyze_repository(), call_tool(), _entity_counts(), find_patterns(), load_and_scan(), get_file() (+52 more)

### Community 1 - "GitHub API Client"
Cohesion: 0.05
Nodes (39): GitHubAPIError, GitHubService, fetch(), is_denied_path(), is_valid_branch(), parse_github_url(), blob(), downloads() (+31 more)

### Community 2 - "MCP Stdio Server"
Cohesion: 0.05
Nodes (33): main(), input_schema(), BackendUnreachable, build_server(), on_list_tools(), Config, default_client_factory(), run_stdio() (+25 more)

### Community 3 - "WebSocket Live Updates"
Cohesion: 0.06
Nodes (22): api_key_is_valid(), _error_frame(), _key_from_subprotocols(), _now_iso(), _parse_client_message(), repository_status_websocket(), _send_json(), WebSocketManager (+14 more)

### Community 4 - "Performance Monitoring"
Cohesion: 0.06
Nodes (11): monitor_repository_processing(), PerformanceMetrics, PerformanceMonitor, reset_global_monitor(), test_concurrent_operations_do_not_collide(), test_endpoints_return_200_quickly(), test_health_computes_system_metrics_once(), test_history_is_bounded() (+3 more)

### Community 5 - "Frontend API Errors"
Cohesion: 0.07
Nodes (24): DescribedError, detailToString(), MCPToolError, AuthErrorListener, authErrorListeners, CodeSageAPI, notifyAuthError(), resolveBaseURL() (+16 more)

### Community 6 - "Prod Docker Compose"
Cohesion: 0.05
Nodes (40): VITE_API_BASE_URL, build, condition, container_name, env_file, environment, healthcheck, networks (+32 more)

### Community 7 - "Claude Desktop Installer"
Cohesion: 0.08
Nodes (16): reset_performance_metrics(), run(), test_backup_is_a_byte_for_byte_copy(), test_basic_auth_stores_password_in_keychain_and_only_user_in_config(), test_creates_config_when_missing(), test_custom_name(), test_dry_run_masks_key_and_writes_nothing(), test_merges_and_preserves_other_servers_and_keys() (+8 more)

### Community 8 - "Dashboard UI Components"
Cohesion: 0.22
Nodes (27): RepositoryStats(), SearchInterface(), SearchInterfaceProps, AnimatedProgress(), AnimatedProgressProps, Button(), buttonVariants, Card() (+19 more)

### Community 9 - "Frontend WebSocket Client"
Cohesion: 0.11
Nodes (10): buildWebSocketProtocols(), buildWebSocketUrl(), ConnectionStatus, ConnectionStatusCallback, RepositoryStatusUpdate, StatusUpdateCallback, FakeWebSocket, WebSocketMessage (+2 more)

### Community 10 - "Repository Ingestion Service"
Cohesion: 0.12
Nodes (23): GitHubFile, RepositoryService, github_file(), make_repository(), test_a_cancelled_delete_keeps_the_slot_until_its_row_clear_finishes(), commit(), test_a_crashed_job_does_not_stay_processing(), test_a_failed_batch_completes_but_says_what_is_missing() (+15 more)

### Community 11 - "Code Parser Tests"
Cohesion: 0.15
Nodes (31): by_name(), parse(), test_body_is_capped_in_characters(), test_body_is_capped_in_lines(), test_c(), test_commonjs_require_is_an_import(), test_cpp(), test_csharp() (+23 more)

### Community 12 - "Alembic Migration Scripts"
Cohesion: 0.11
Nodes (4): upgrade(), downgrade(), downgrade(), _configure_sqlite()

### Community 13 - "Algolia Indexing"
Cohesion: 0.10
Nodes (7): AlgoliaService, delete(), save(), _fit_record(), test_facet_values_cannot_add_filter_clauses(), test_indented_definitions_hold_their_signature_once(), test_search_scopes_by_repository_with_a_numeric_filter()

### Community 14 - "Dev Docker Compose"
Cohesion: 0.06
Nodes (32): VITE_API_BASE_URL, VITE_CODESAGE_API_KEY, build, command, container_name, env_file, environment, healthcheck (+24 more)

### Community 15 - "App Shell & UI Tests"
Cohesion: 0.14
Nodes (17): App(), Toast, ToastContainer(), ToastContext, ToastContextType, ToastItem(), ToastProvider(), repository (+9 more)

### Community 17 - "CI Workflow"
Cohesion: 0.08
Nodes (28): defaults, runs-on, steps, run, runs-on, steps, defaults, runs-on (+20 more)

### Community 18 - "Algolia Test Fixtures"
Cohesion: 0.09
Nodes (8): algolia_index(), client(), db_engine(), db_session(), FakeGitHub, github(), job_sessions(), reset_rate_limits()

### Community 19 - "Repository REST Endpoints"
Cohesion: 0.11
Nodes (9): create_repository(), delete_repository(), get_repository(), get_repository_stats(), get_repository_status(), list_repositories(), process_repository(), Repository (+1 more)

### Community 21 - "API Security Guard"
Cohesion: 0.11
Nodes (6): BrowserRequestGuard, _hostname(), _is_loopback_peer(), request_refusal(), require_api_key(), lifespan()

### Community 22 - "Repository Job Errors"
Cohesion: 0.11
Nodes (7): IngestionError, is_processing(), RepositoryBusyError, start_processing(), test_a_repository_never_runs_two_jobs_at_once(), test_no_run_can_start_while_a_delete_is_in_flight(), busy()

### Community 23 - "TS App Config"
Cohesion: 0.09
Nodes (22): compilerOptions, allowImportingTsExtensions, baseUrl, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+14 more)

### Community 24 - "Database Migration Runner"
Cohesion: 0.25
Nodes (14): _is_memory_sqlite(), upgrade_database(), _build_legacy(), _cfg(), _counts(), _engine(), test_downgrade_from_head_restores_nullable_columns(), test_downgrade_to_baseline() (+6 more)

### Community 25 - "Settings & Config Validation"
Cohesion: 0.15
Nodes (5): Settings, validate_runtime_settings(), TestErrors, TestRateLimit, TestRuntimeSettings

### Community 26 - "Frontend Runtime Deps"
Cohesion: 0.10
Nodes (21): dependencies, axios@^1.10.0, class-variance-authority@^0.7.1, clsx@^2.1.1, @hookform/resolvers@^6.0.0, @radix-ui/react-slot@^1.2.3, react@^19.1.0, react-dom@^19.1.0 (+13 more)

### Community 27 - "MCP Tools HTTP API"
Cohesion: 0.15
Nodes (9): call_mcp_tool(), get_mcp_capabilities(), get_search_suggestions(), list_mcp_resources(), list_mcp_tools(), MCPToolCallRequest, read_mcp_resource(), get_db() (+1 more)

### Community 28 - "Alembic Env & Settings"
Cohesion: 0.15
Nodes (10): get_url(), run_migrations_offline(), run_migrations_online(), get_settings(), api_key(), key_protocols(), test_search_suggestions_require_the_key_and_are_rate_limited(), test_tool_call_is_rate_limited() (+2 more)

### Community 30 - "TS Node Config"
Cohesion: 0.11
Nodes (18): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, moduleResolution, noEmit (+10 more)

### Community 31 - "Async Job Recovery"
Cohesion: 0.14
Nodes (7): _fail_if_still_processing(), _run_job(), _run_slot(), _to_thread_to_completion(), test_run_slots_work_on_every_event_loop(), contend(), hold()

### Community 32 - "Architecture & Data Model"
Cohesion: 0.16
Nodes (15): aiohttp==3.14.5, algoliasearch==3.0.0, tree-sitter-language-pack==1.22.1, Architecture, code_entities table, code_files table, /health endpoint, repositories table (+7 more)

### Community 33 - "Processing Pipeline Tests"
Cohesion: 0.22
Nodes (14): github_file(), process(), repository(), stored_counts(), test_entities_from_other_repositories_are_untouched(), test_failed_fetch_during_reprocess_keeps_the_existing_index(), test_github_errors_mark_the_run_failed(), test_repository_with_no_code_files_fails() (+6 more)

### Community 34 - "shadcn Components Config"
Cohesion: 0.11
Nodes (17): aliases, components, hooks, lib, ui, utils, iconLibrary, rsc (+9 more)

### Community 35 - "Frontend Dev Deps"
Cohesion: 0.11
Nodes (18): devDependencies, jsdom@^30.1.3, postcss@^8.5.6, tailwindcss@^3.4.17, @testing-library/dom@^10.4.2, @testing-library/jest-dom@^7.0.1, @testing-library/react@^16.3.3, @testing-library/user-event@^14.6.8 (+10 more)

### Community 36 - "Performance API Endpoints"
Cohesion: 0.15
Nodes (6): export_performance_metrics(), get_operation_performance(), get_performance_metrics(), get_system_metrics(), performance_health_check(), PerformanceReportResponse

### Community 37 - "Repository Schemas"
Cohesion: 0.18
Nodes (5): update_repository(), RepositoryBase, RepositoryCreate, RepositoryResponse, RepositoryUpdate

### Community 38 - "Algolia Service Tests"
Cohesion: 0.15
Nodes (11): _PendingTask, record_bytes(), test_an_unpublished_delete_fails_instead_of_hanging(), test_an_unpublished_save_does_not_hang_indexing(), test_delete_removes_only_that_repositorys_records(), test_long_docstring_record_stays_under_the_size_limit(), test_oversized_record_trims_content_to_fit(), test_repository_stats_use_a_numeric_filter() (+3 more)

### Community 39 - "GitHub URL Form"
Cohesion: 0.17
Nodes (10): extractRepoName(), GitHubForm(), GitHubFormData, GitHubFormProps, githubUrlSchema, CardDescription(), queryClient, shouldRetryQuery() (+2 more)

### Community 40 - "Python AST Extraction"
Cohesion: 0.15
Nodes (3): LanguageSpec, make_body(), _spec()

### Community 41 - "MCP Integration Docs"
Cohesion: 0.15
Nodes (14): mcp==2.3.0, GET /api/v1/ai/mcp/capabilities, claude_desktop_config.json, codesage://repositories resource, MCP Inspector, MCP integration guide, MCP_SERVER_URL, GET /api/v1/ai/mcp/resources (+6 more)

### Community 42 - "MCP API Tests"
Cohesion: 0.16
Nodes (8): call(), test_call_bad_arguments_422(), test_call_success_shape(), test_call_tool_error_is_200_with_is_error(), test_call_unknown_tool_404(), test_reading_a_resource_requires_the_key(), test_suggestions_algolia_unavailable(), test_suggestions_distinct()

### Community 43 - "Product Overview & MCP Tools"
Cohesion: 0.14
Nodes (14): find_patterns tool, Algolia MCP Server Challenge, analyze_repository tool, Claude Desktop, CodeSage, docs/architecture.md link, find_patterns tool, get_file tool (+6 more)

### Community 44 - "Backend Dependencies"
Cohesion: 0.14
Nodes (14): Backend dev/test dependencies, pytest==9.1.1, pytest-asyncio==1.4.0, ruff==0.17.2, httpx2==2.16.0, psutil==7.2.2, pydantic==2.14.1, pydantic-settings==2.16.1 (+6 more)

### Community 45 - "Frontend Package Meta"
Cohesion: 0.14
Nodes (13): description, autoprefixer@^10.4.21, @tanstack/react-query-devtools@^5.83.0, @types/node@^24.0.15, @types/react-dom@^19.1.6, name, private, type (+5 more)

### Community 48 - "ESLint Setup"
Cohesion: 0.15
Nodes (12): eslint@^9.30.1, @eslint/js@^9.30.1, eslint-plugin-react-hooks@^5.2.0, eslint-plugin-react-refresh@^0.4.20, globals@^16.3.0, typescript-eslint@^8.35.1, eslint, @eslint/js (+4 more)

### Community 49 - "Layout & Connection Status"
Cohesion: 0.27
Nodes (9): Layout(), LayoutProps, ConnectionStatus(), Trigger(), useToast(), getPageTitle(), usePageTitle(), useGlobalToasts() (+1 more)

### Community 51 - "Proxy & Key Test Fixtures"
Cohesion: 0.21
Nodes (4): api_key(), _isolate(), TestBehindTheProdProxy, create()

### Community 52 - "Status Polling Fallback"
Cohesion: 0.29
Nodes (7): RepositoryStatsProps, UseRealtimeStatusOptions, isActiveStatus(), POLL_INTERVAL_MS, pollWhileActive(), pollWhileAnyActive(), Repository

### Community 53 - "Security Model Docs"
Cohesion: 0.20
Nodes (9): alembic==1.20.1, fastapi==0.161.1, slowapi==0.1.10, BrowserRequestGuard (app/core/security.py), Constant-time API key comparison, Security model, vite.config.ts proxy, Alembic migrations (+1 more)

### Community 54 - "Docker Deployment Docs"
Cohesion: 0.20
Nodes (8): backend_data volume, backend container service, Docker deployment, nginx container service, ALGOLIA_INDEX_NAME, CI workflow (.github/workflows/ci.yml), Docker Compose stack, nginx

### Community 55 - "Production Auth & TLS"
Cohesion: 0.18
Nodes (7): CODESAGE_ALLOW_INSECURE_AUTH, macOS Keychain (codesage-mcp), Production compose (docker-compose.prod.yml), HTTPS / TLS on 443, Real-time updates (/ws), React Dashboard, /ws WebSocket endpoint

### Community 56 - "Frontend Entry & Stack"
Cohesion: 0.20
Nodes (9): CodeSage - MCP-First Code Discovery (index.html), /src/main.tsx entry, Axios, CodeSage frontend, React Router, Tailwind CSS, TanStack Query, Vite (+1 more)

### Community 60 - "Health Check"
Cohesion: 0.29
Nodes (3): _check_algolia(), health_check(), root()

### Community 61 - "Vite Build Config"
Cohesion: 0.33
Nodes (4): vite@^7.0.4, @vitejs/plugin-react@^4.6.0, vite, @vitejs/plugin-react

### Community 62 - "NPM Scripts"
Cohesion: 0.33
Nodes (6): scripts, build, dev, lint, preview, test

### Community 66 - "Favicon Brand Icon"
Cohesion: 0.67
Nodes (3): brainGradient (indigo-violet gradient), CodeSage Favicon (Brain Icon), Neural Network Motif

## Knowledge Gaps
- **43 isolated node(s):** `Model Context Protocol (MCP)`, `Algolia MCP Server Challenge`, `SQLite`, `Python ast parser`, `doc_section entity` (+38 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 574 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CODESAGE_API_KEY` connect `Production Auth & TLS` to `MCP Integration Docs`, `Product Overview & MCP Tools`, `Security Model Docs`?**
  _High betweenness centrality (0.253) - this node is a cross-community bridge._
- **Are the 23 inferred relationships involving `Repository` (e.g. with `create_repository()` and `delete_repository()`) actually correct?**
  _`Repository` has 23 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Model Context Protocol (MCP)`, `Algolia MCP Server Challenge`, `SQLite` to the rest of the system?**
  _43 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Code Entity Model` be split into smaller, more focused modules?**
  _Cohesion score 0.05198537095088819 - nodes in this community are weakly interconnected._
- **Why does `make install-claude` connect `Product Overview & MCP Tools` to `Claude Desktop Installer`, `Production Auth & TLS`?**
  _High betweenness centrality (0.232) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `RepositoryService` (e.g. with `create_repository()` and `delete_repository()`) actually correct?**
  _`RepositoryService` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Should `GitHub API Client` be split into smaller, more focused modules?**
  _Cohesion score 0.051131354687040845 - nodes in this community are weakly interconnected._