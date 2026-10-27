import { useState, useRef, useEffect, useId } from "react";
import { isCancel } from "axios";
import { api } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { describeError, type DescribedError } from "@/lib/errors";
import { isHttpUrl } from "@/lib/utils";
import type { SearchHit } from "@/types/mcp";
import type { RepositoryStatus } from "@/types/repository";

interface SearchInterfaceProps {
  repositoryId: number;
  canSearch: boolean;
  status?: RepositoryStatus;
  className?: string;
}

const PAGE_SIZE = 10;
const BLUR_CLOSE_MS = 150;

export function SearchInterface({
  repositoryId,
  canSearch,
  status,
  className,
}: SearchInterfaceProps) {
  const listboxId = useId();
  const [searchQuery, setSearchQuery] = useState("");
  // The query that produced the current results (pagination must reuse it,
  // not whatever is currently typed in the input).
  const [activeQuery, setActiveQuery] = useState("");
  const [hasSearched, setHasSearched] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchHit[]>([]);
  const [isSearching, setIsSearching] = useState(false);
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
  const suppressedFor = useRef<string | null>(null);

  useEffect(() => () => clearTimeout(blurTimer.current), []);

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
    }, 300);
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timeoutId);
    };
  }, [searchQuery, canSearch, repositoryId]);

  const runSearch = async (query: string, targetPage: number) => {
    const trimmed = query.trim();
    if (!trimmed || !canSearch) return;

    const requestId = ++searchRequestId.current;
    suppressedFor.current = query;
    setShowSuggestions(false);
    setIsSearching(true);
    setSearchError(null);

    try {
      const response = await api.searchCode({
        query: trimmed,
        repository: String(repositoryId),
        limit: PAGE_SIZE,
        page: targetPage,
      });
      if (requestId !== searchRequestId.current) return; // superseded
      setSearchResults(response.results);
      setTotalHits(response.total_hits);
      setPages(response.pages);
      setPage(response.page ?? targetPage);
      setActiveQuery(trimmed);
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
      if (requestId === searchRequestId.current) setIsSearching(false);
    }
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
            ? "Search functions, classes, imports and docs in this repository"
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
                  className="absolute top-full left-0 right-0 mt-1 bg-white border rounded-md shadow-lg z-10"
                >
                  {suggestions.map((suggestion, index) => (
                    <div
                      key={suggestion}
                      id={`${listboxId}-${index}`}
                      role="option"
                      aria-selected={index === active}
                      className={`w-full text-left px-3 py-2 hover:bg-gray-50 text-sm cursor-pointer ${
                        index === active ? "bg-gray-100" : ""
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

        {searchError && (
          <div
            role="alert"
            className={`p-4 rounded-md border ${
              searchError.kind === "network"
                ? "bg-red-50 border-red-200"
                : "bg-orange-50 border-orange-200"
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
                <p className="text-sm text-gray-600">{searchError.message}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                aria-label="Dismiss error"
                onClick={() => setSearchError(null)}
                className="text-gray-400 hover:text-gray-600"
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
                Found {totalHits.toLocaleString()} result
                {totalHits !== 1 ? "s" : ""} for &ldquo;{activeQuery}&rdquo;
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
                key={`${result.file_path}:${result.line_start}:${result.entity_name}`}
                className="hover:shadow-md transition-shadow"
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-2 gap-2">
                    <h4 className="font-medium text-lg break-all">
                      {isHttpUrl(result.url) ? (
                        <a
                          href={result.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline"
                        >
                          {result.entity_name}
                        </a>
                      ) : (
                        result.entity_name
                      )}
                    </h4>
                    {result.entity_type && (
                      <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded text-xs">
                        {result.entity_type}
                      </span>
                    )}
                  </div>

                  <div className="space-y-2">
                    {result.description && (
                      <p className="text-sm text-muted-foreground">
                        {result.description}
                      </p>
                    )}

                    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
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
                      <div className="mt-2 p-2 bg-gray-50 rounded text-xs font-mono overflow-x-auto">
                        <pre className="whitespace-pre-wrap">
                          {result.snippet}
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
