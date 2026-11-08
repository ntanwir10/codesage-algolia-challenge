import { useState, useRef, useEffect, useId } from "react";
import { isCancel } from "axios";
import { api } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { describeError, type DescribedError } from "@/lib/errors";
import { ENTITY_TYPES, fileViewerPath, isHttpUrl } from "@/lib/utils";
import { Link, useSearchParams } from "react-router-dom";
import { Highlight } from "@/components/ui/highlight";
import type { EntityType, SearchHit, SearchMode } from "@/types/mcp";
import type { RepositoryStatus } from "@/types/repository";

interface SearchInterfaceProps {
  /** Omit to search every indexed repository */
  repositoryId?: number;
  canSearch: boolean;
  status?: RepositoryStatus;
  /** Languages with indexed entities, offered as a filter */
  languages?: string[];
  className?: string;
}

const PAGE_SIZE = 10;
const BLUR_CLOSE_MS = 150;
// Each semantic suggestion costs an embeddings call, so wait a little longer for typing to stop
const SUGGEST_DELAY_MS = { keyword: 300, semantic: 500 };

export function SearchInterface({
  repositoryId,
  canSearch,
  status,
  languages = [],
  className,
}: SearchInterfaceProps) {
  const listboxId = useId();
  const [params, setParams] = useSearchParams();
  // A query in the URL (a reload, or Back from the file viewer) runs once search is possible
  const urlQuery = params.get("q") ?? "";
  const [searchQuery, setSearchQuery] = useState(urlQuery);
  const [language, setLanguage] = useState("");
  const [entityType, setEntityType] = useState<EntityType | "">("");
  // Kept in the URL with the query, so Back from the file viewer returns to the same ranking
  const [mode, setMode] = useState<SearchMode>(params.get("mode") === "semantic" ? "semantic" : "keyword");
  const [semanticAvailable, setSemanticAvailable] = useState(false);
  // Whether the shown results came from a semantic search (they rank everything, so no count)
  const [rankedByMeaning, setRankedByMeaning] = useState(false);
  // The query that produced the current results (pagination must reuse it,
  // not whatever is currently typed in the input).
  const [activeQuery, setActiveQuery] = useState("");
  const [hasSearched, setHasSearched] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchHit[]>([]);
  const [searchPending, setSearchPending] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(-1); // keyboard highlight; -1 for none
  const [searchError, setSearchError] = useState<DescribedError | null>(null);
  const [page, setPage] = useState(0); // zero-based, as the server expects
  const [pages, setPages] = useState(0);
  const [totalHits, setTotalHits] = useState(0);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined
  );
  const searchRequestId = useRef(0);
  // Query for which suggestions should stay hidden (just searched/selected).
  // Starts as the URL's query, which is about to be searched.
  const suppressedFor = useRef<string | null>(urlQuery);

  useEffect(() => () => clearTimeout(blurTimer.current), []);

  // Offer search by meaning only when the server has an embeddings key
  useEffect(() => {
    let cancelled = false;
    api
      .getCapabilities()
      .then((caps) => {
        if (!cancelled) setSemanticAvailable(caps.semantic_search === true);
      })
      .catch(() => {}); // keyword search still works
    return () => {
      cancelled = true;
    };
  }, []);

  // Debounced suggestions; stale responses are aborted and ignored.
  useEffect(() => {
    if (!canSearch || searchQuery.length <= 2 || suppressedFor.current === searchQuery) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    const timeoutId = setTimeout(async () => {
      try {
        const result = await api.getSearchSuggestions(searchQuery, {
          repositoryId,
          limit: 5,
          mode,
          signal: controller.signal,
        });
        // A search submitted after the timer started doesn't change searchQuery,
        // so this effect wasn't cleaned up; don't reopen over the results.
        if (cancelled || suppressedFor.current === searchQuery) return;
        setSuggestions(result);
        setShowSuggestions(result.length > 0);
      } catch (error: unknown) {
        if (cancelled || isCancel(error)) return;
        setSuggestions([]);
        setShowSuggestions(false);
      }
    }, SUGGEST_DELAY_MS[mode]);
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timeoutId);
    };
  }, [searchQuery, canSearch, repositoryId, mode]);

  // Filters are passed in when they have just changed, as state still holds the old ones
  const runSearch = async (query: string, targetPage: number, filters = { language, entityType, mode }) => {
    if (!query.trim() || !canSearch) return;
    suppressedFor.current = query;
    setShowSuggestions(false);
    setSearchPending(true);
    setSearchError(null);
    await fetchResults(query, targetPage, filters);
  };

  // Sets state only once the response is in, so the URL's search can run from an effect
  const fetchResults = async (query: string, targetPage: number, filters = { language, entityType, mode }) => {
    const trimmed = query.trim();
    const requestId = ++searchRequestId.current;
    try {
      const response = await api.searchCode({
        query: trimmed,
        repository: repositoryId ? String(repositoryId) : undefined,
        language: filters.language || undefined,
        entity_type: filters.entityType || undefined,
        limit: PAGE_SIZE,
        page: targetPage,
        mode: filters.mode,
      });
      if (requestId !== searchRequestId.current) return; // superseded
      setSearchError(null); // the URL's search skips runSearch's reset
      setSearchResults(response.results);
      setRankedByMeaning(response.mode === "semantic");
      setTotalHits(response.total_hits);
      setPages(response.pages);
      setPage(response.page ?? targetPage);
      setActiveQuery(trimmed);
      // Keep the query in the URL (replacing, not adding, a history entry) so reload and Back keep it
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.set("q", trimmed);
          if (filters.mode === "semantic") next.set("mode", "semantic");
          else next.delete("mode");
          return next;
        },
        { replace: true }
      );
      setHasSearched(true);
    } catch (error: unknown) {
      if (requestId !== searchRequestId.current) return;
      setSearchError(describeError(error));
      // A failed page change keeps the current results and pager.
      if (targetPage === 0) {
        setSearchResults([]);
        setTotalHits(0);
        setPages(0);
      }
      setHasSearched(true);
    } finally {
      if (requestId === searchRequestId.current) setSearchPending(false);
    }
  };

  useEffect(() => {
    if (urlQuery.trim() && canSearch && !activeQuery) void fetchResults(urlQuery, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when search becomes possible
  }, [canSearch]);
  // The effect can't set searchPending, so the URL's first search counts as pending until it lands
  const isSearching = searchPending || (canSearch && urlQuery.trim() !== "" && !hasSearched);

  // A filter change re-runs the shown search from its first page
  const changeFilters = (change: Partial<{ language: string; entityType: EntityType | ""; mode: SearchMode }>) => {
    const filters = { language, entityType, mode, ...change };
    setLanguage(filters.language);
    setEntityType(filters.entityType);
    setMode(filters.mode);
    if (activeQuery) void runSearch(activeQuery, 0, filters);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void runSearch(searchQuery, 0);
  };

  const handleSuggestionClick = (suggestion: string) => {
    setSearchQuery(suggestion);
    void runSearch(suggestion, 0);
    searchInputRef.current?.focus();
  };

  const hasNext = page + 1 < pages;
  const hasPrev = page > 0;
  const suggestionsOpen = showSuggestions && suggestions.length > 0;
  const active = suggestionsOpen && activeSuggestion < suggestions.length ? activeSuggestion : -1;

  // Combobox keys: arrows move through the suggestions, Enter picks one, Escape closes the list
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!suggestionsOpen) return;
    const count = suggestions.length;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActiveSuggestion(
        active < 0 ? (step > 0 ? 0 : count - 1) : (active + step + count) % count
      );
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      setShowSuggestions(false);
      handleSuggestionClick(suggestions[active]);
    } else if (e.key === "Escape") {
      setShowSuggestions(false);
    }
  };

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span>🔍</span>
          AI-Powered Code Search
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          {canSearch
            ? repositoryId
              ? "Search functions, classes, imports and docs in this repository"
              : "Search every indexed repository at once"
            : status === "failed"
            ? "Indexing failed, so search isn't available. Reprocess the repository to try again."
            : "Search will be available once processing is complete"}
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleSubmit}>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Input
                ref={searchInputRef}
                role="combobox"
                aria-label="Search query"
                aria-expanded={suggestionsOpen}
                aria-controls={listboxId}
                aria-autocomplete="list"
                aria-activedescendant={active >= 0 ? `${listboxId}-${active}` : undefined}
                autoComplete="off"
                // The server caps queries at 512 bytes; 170 UTF-16 units is at most 510
                maxLength={170}
                placeholder="Search your code... (e.g., 'authentication middleware')"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setActiveSuggestion(-1);
                }}
                onKeyDown={handleKeyDown}
                onFocus={() => {
                  clearTimeout(blurTimer.current);
                  setShowSuggestions(suggestions.length > 0);
                }}
                onBlur={() => {
                  clearTimeout(blurTimer.current);
                  blurTimer.current = setTimeout(
                    () => setShowSuggestions(false),
                    BLUR_CLOSE_MS
                  );
                }}
                disabled={!canSearch}
                className="pr-4"
              />

              {suggestionsOpen && (
                <div
                  id={listboxId}
                  role="listbox"
                  aria-label="Search suggestions"
                  className="absolute top-full left-0 right-0 mt-1 bg-popover text-popover-foreground border rounded-md shadow-lg z-10"
                >
                  {suggestions.map((suggestion, index) => (
                    <div
                      key={suggestion}
                      id={`${listboxId}-${index}`}
                      role="option"
                      aria-selected={index === active}
                      className={`w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-900 text-sm cursor-pointer ${
                        index === active ? "bg-gray-100 dark:bg-gray-800" : ""
                      }`}
                      // mousedown fires before blur, so the click is not lost
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => handleSuggestionClick(suggestion)}
                    >
                      {suggestion}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <Button
              type="submit"
              disabled={!canSearch || isSearching || !searchQuery.trim()}
              className="px-6"
            >
              {isSearching ? <LoadingSpinner className="w-4 h-4" /> : "Search"}
            </Button>
          </div>
        </form>

        {canSearch && (
          <div className="flex flex-wrap gap-2 text-sm">
            <select
              aria-label="Filter by language"
              value={language}
              onChange={(e) => changeFilters({ language: e.target.value })}
              className="border rounded-md px-2 py-1 bg-background"
            >
              <option value="">All languages</option>
              {languages.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter by kind"
              value={entityType}
              onChange={(e) => changeFilters({ entityType: e.target.value as EntityType | "" })}
              className="border rounded-md px-2 py-1 bg-background"
            >
              <option value="">All kinds</option>
              {ENTITY_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            {semanticAvailable && (
              <select
                aria-label="Search mode"
                value={mode}
                onChange={(e) => changeFilters({ mode: e.target.value as SearchMode })}
                className="border rounded-md px-2 py-1 bg-background"
              >
                <option value="keyword">Keyword</option>
                <option value="semantic">By meaning</option>
              </select>
            )}
          </div>
        )}

        {searchError && (
          <div
            role="alert"
            className={`p-4 rounded-md border ${
              searchError.kind === "network"
                ? "bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-800"
                : "bg-orange-50 dark:bg-orange-950/40 border-orange-200 dark:border-orange-800"
            }`}
          >
            <div className="flex items-start justify-between">
              <div>
                <h4 className="font-medium text-sm mb-1">
                  {searchError.kind === "network"
                    ? "Connection Error"
                    : searchError.kind === "tool"
                    ? "Search failed"
                    : "Service Error"}
                </h4>
                <p className="text-sm text-gray-600 dark:text-gray-300">{searchError.message}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                aria-label="Dismiss error"
                onClick={() => setSearchError(null)}
                className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
              >
                ✕
              </Button>
            </div>
          </div>
        )}

        {searchResults.length > 0 && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                {rankedByMeaning ? (
                  <>Ranked by meaning for &ldquo;{activeQuery}&rdquo;</>
                ) : (
                  <>
                    Found {totalHits.toLocaleString()} result
                    {totalHits !== 1 ? "s" : ""} for &ldquo;{activeQuery}&rdquo;
                  </>
                )}
              </p>

              {pages > 1 && (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void runSearch(activeQuery, page - 1)}
                    disabled={!hasPrev || isSearching}
                  >
                    Previous
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    Page {page + 1} of {pages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void runSearch(activeQuery, page + 1)}
                    disabled={!hasNext || isSearching}
                  >
                    Next
                  </Button>
                </div>
              )}
            </div>

            {searchResults.map((result) => (
              <Card
                key={`${result.repository_id}:${result.file_path}:${result.line_start}:${result.entity_name}`}
                className="hover:shadow-md transition-shadow"
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-2 gap-2">
                    <h4 className="font-medium text-lg break-all">
                      {(repositoryId ?? result.repository_id) ? (
                        <Link
                          to={fileViewerPath(
                            (repositoryId ?? result.repository_id) as number,
                            result.file_path,
                            result.line_start,
                            result.line_end
                          )}
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          <Highlight text={result.entity_name} query={activeQuery} />
                        </Link>
                      ) : (
                        <Highlight text={result.entity_name} query={activeQuery} />
                      )}
                      {isHttpUrl(result.url) && (
                        <a
                          href={result.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-2 text-xs font-normal text-muted-foreground hover:underline"
                        >
                          source ↗
                        </a>
                      )}
                    </h4>
                    <div className="flex shrink-0 flex-wrap justify-end gap-1">
                      {result.score !== undefined && (
                        <span
                          title="Cosine similarity between your query and this definition; higher is closer"
                          className="bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 px-2 py-1 rounded text-xs"
                        >
                          similarity {result.score.toFixed(2)}
                        </span>
                      )}
                      {result.entity_type && (
                        <span className="bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 px-2 py-1 rounded text-xs">
                          {result.entity_type}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="space-y-2">
                    {result.description && (
                      <p className="text-sm text-muted-foreground">
                        <Highlight text={result.description} query={activeQuery} />
                      </p>
                    )}

                    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                      {!repositoryId && result.repository && <span>📦 {result.repository}</span>}
                      <span>📁 {result.file_path}</span>
                      {result.language && <span>🔤 {result.language}</span>}
                      <span>
                        📍 Lines {result.line_start}-{result.line_end}
                      </span>
                    </div>

                    {/* The snippet usually starts with the signature; don't show it twice */}
                    {result.signature &&
                      !result.snippet?.trimStart().startsWith(result.signature.trim()) && (
                        <code className="block text-xs font-mono break-all">
                          {result.signature}
                        </code>
                      )}

                    {result.snippet && (
                      <div className="mt-2 p-2 bg-gray-50 dark:bg-gray-900 rounded text-xs font-mono overflow-x-auto">
                        <pre className="whitespace-pre">
                          <Highlight text={result.snippet} query={activeQuery} />
                        </pre>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {hasSearched &&
          !isSearching &&
          searchResults.length === 0 &&
          !searchError && (
            <div className="text-center py-8">
              <div className="text-4xl mb-2">🔍</div>
              <h3 className="font-medium mb-1">No results found</h3>
              <p className="text-sm text-muted-foreground">
                Try different keywords or a more specific query.
              </p>
            </div>
          )}

        {isSearching && (
          <div className="py-8">
            <LoadingSpinner text="Searching your codebase..." />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
