import { useState, useRef, useEffect } from "react";
import { api } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import type { SearchHit } from "@/types/mcp";

interface SearchInterfaceProps {
  repositoryId: number;
  canSearch: boolean;
  className?: string;
}

interface SearchError {
  message: string;
  type: "network" | "api" | "suggestions" | "general";
}

export function SearchInterface({
  repositoryId,
  canSearch,
  className,
}: SearchInterfaceProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchHit[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [searchError, setSearchError] = useState<SearchError | null>(null);
  const [suggestionsError, setSuggestionsError] = useState<string>("");
  const [currentPage, setCurrentPage] = useState(1);
  const [totalResults, setTotalResults] = useState(0);
  const [hasMoreResults, setHasMoreResults] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const resultsPerPage = 10;

  // Get search suggestions as user types
  useEffect(() => {
    const getSuggestions = async () => {
      if (searchQuery.length > 2 && canSearch) {
        try {
          setSuggestionsError("");
          const suggestions = await api.getSearchSuggestions(searchQuery);
          setSuggestions(suggestions.slice(0, 5));
          setShowSuggestions(true);
        } catch (error: unknown) {
          console.error("Error getting suggestions:", error);
          setSuggestionsError("Unable to load suggestions");
          setSuggestions([]);
          setShowSuggestions(false);
        }
      } else {
        setSuggestions([]);
        setShowSuggestions(false);
        setSuggestionsError("");
      }
    };

    const timeoutId = setTimeout(getSuggestions, 300); // Debounce
    return () => clearTimeout(timeoutId);
  }, [searchQuery, canSearch]);

  const getErrorMessage = (error: unknown): SearchError => {
    if (!error) {
      return { message: "An unknown error occurred", type: "general" };
    }

    // Type guard for axios error structure
    const isAxiosError = (
      err: unknown
    ): err is {
      code?: string;
      message?: string;
      response?: {
        status: number;
        data?: { detail?: string; message?: string };
      };
    } => {
      return typeof err === "object" && err !== null;
    };

    if (isAxiosError(error)) {
      // Network errors
      if (error.code === "NETWORK_ERROR" || error.message === "Network Error") {
        return {
          message:
            "Unable to connect to the server. Please check your connection.",
          type: "network",
        };
      }

      // API errors
      if (error.response) {
        const status = error.response.status;
        const data = error.response.data;

        switch (status) {
          case 404:
            return {
              message: "Search service not found. Please contact support.",
              type: "api",
            };
          case 429:
            return {
              message: "Too many requests. Please wait a moment and try again.",
              type: "api",
            };
          case 500:
            return {
              message: "Server error. Please try again later.",
              type: "api",
            };
          default:
            return {
              message: data?.detail || data?.message || `Error: ${status}`,
              type: "api",
            };
        }
      }

      return {
        message: error.message || "Search failed. Please try again.",
        type: "general",
      };
    }

    return {
      message: "Search failed. Please try again.",
      type: "general",
    };
  };

  const handleSearch = async (query?: string, page: number = 1) => {
    const queryToSearch = query || searchQuery;
    if (!queryToSearch.trim() || !canSearch) return;

    setIsSearching(true);
    setShowSuggestions(false);
    setSearchError(null);

    try {
      const results = await api.searchCode({
        query: queryToSearch,
        repository_id: repositoryId,
        per_page: resultsPerPage,
        page: page,
      });

      setSearchResults(results.hits || []);
      setTotalResults(results.total || 0);
      setCurrentPage(page);
      setHasMoreResults((results.total || 0) > page * resultsPerPage);

      if (query) {
        setSearchQuery(query);
      }
    } catch (error: unknown) {
      console.error("Search error:", error);
      const searchError = getErrorMessage(error);
      setSearchError(searchError);
      setSearchResults([]);
      setTotalResults(0);
      setHasMoreResults(false);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
    handleSearch();
  };

  const handleSuggestionClick = (suggestion: string) => {
    setCurrentPage(1);
    handleSearch(suggestion);
    searchInputRef.current?.focus();
  };

  const handleNextPage = () => {
    if (hasMoreResults) {
      handleSearch(searchQuery, currentPage + 1);
    }
  };

  const handlePrevPage = () => {
    if (currentPage > 1) {
      handleSearch(searchQuery, currentPage - 1);
    }
  };

  const clearError = () => {
    setSearchError(null);
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
            ? "Ask natural language questions about your code"
            : "Search will be available once processing is complete"}
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="relative">
          <form onSubmit={handleSubmit}>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Input
                  ref={searchInputRef}
                  placeholder="Ask anything about your code... (e.g., 'How does authentication work?')"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onFocus={() => setShowSuggestions(suggestions.length > 0)}
                  onBlur={() =>
                    setTimeout(() => setShowSuggestions(false), 200)
                  }
                  disabled={!canSearch}
                  className="pr-4"
                />

                {/* Search Suggestions */}
                {showSuggestions && suggestions.length > 0 && (
                  <div className="absolute top-full left-0 right-0 mt-1 bg-white border rounded-md shadow-lg z-10">
                    {suggestions.map((suggestion, index) => (
                      <button
                        key={index}
                        type="button"
                        className="w-full text-left px-3 py-2 hover:bg-gray-50 text-sm"
                        onClick={() => handleSuggestionClick(suggestion)}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                )}

                {/* Suggestions Error */}
                {suggestionsError && (
                  <div className="absolute top-full left-0 right-0 mt-1 bg-yellow-50 border border-yellow-200 rounded-md p-2 text-sm text-yellow-700 z-10">
                    {suggestionsError}
                  </div>
                )}
              </div>

              <Button
                type="submit"
                disabled={!canSearch || isSearching}
                className="px-6"
              >
                {isSearching ? (
                  <LoadingSpinner className="w-4 h-4" />
                ) : (
                  "Search"
                )}
              </Button>
            </div>
          </form>
        </div>

        {/* Search Error Display */}
        {searchError && (
          <div
            className={`p-4 rounded-md border ${
              searchError.type === "network"
                ? "bg-red-50 border-red-200"
                : searchError.type === "api"
                ? "bg-orange-50 border-orange-200"
                : "bg-yellow-50 border-yellow-200"
            }`}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-2">
                <span className="text-lg">
                  {searchError.type === "network"
                    ? "🔌"
                    : searchError.type === "api"
                    ? "⚠️"
                    : "💡"}
                </span>
                <div>
                  <h4 className="font-medium text-sm mb-1">
                    {searchError.type === "network"
                      ? "Connection Error"
                      : searchError.type === "api"
                      ? "Service Error"
                      : "Search Error"}
                  </h4>
                  <p className="text-sm text-gray-600">{searchError.message}</p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={clearError}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </Button>
            </div>
          </div>
        )}

        {/* Search Results */}
        {searchResults.length > 0 && (
          <div className="space-y-4">
            {/* Results Header */}
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Found {totalResults} result{totalResults !== 1 ? "s" : ""}
                {currentPage > 1 && ` (Page ${currentPage})`}
              </p>

              {/* Pagination Controls */}
              {(currentPage > 1 || hasMoreResults) && (
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handlePrevPage}
                    disabled={currentPage <= 1 || isSearching}
                  >
                    Previous
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    Page {currentPage}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleNextPage}
                    disabled={!hasMoreResults || isSearching}
                  >
                    Next
                  </Button>
                </div>
              )}
            </div>

            {/* Results List */}
            {searchResults.map((result, index) => (
              <Card key={index} className="hover:shadow-md transition-shadow">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <h4 className="font-medium text-lg">
                      {result.entity_name}
                    </h4>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded">
                        Score: {result.relevance_score.toFixed(2)}
                      </span>
                      {result.entity_type && (
                        <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded">
                          {result.entity_type}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="space-y-2">
                    {result.description && (
                      <p className="text-sm text-muted-foreground">
                        {result.description}
                      </p>
                    )}

                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>📁 {result.file_path}</span>
                      {result.language && <span>🔤 {result.language}</span>}
                      {result.line_start && result.line_end && (
                        <span>
                          📍 Lines {result.line_start}-{result.line_end}
                        </span>
                      )}
                    </div>

                    {result.content && (
                      <div className="mt-2 p-2 bg-gray-50 rounded text-xs font-mono">
                        <pre className="whitespace-pre-wrap">
                          {result.content}
                        </pre>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* No Results State */}
        {!isSearching &&
          searchResults.length === 0 &&
          searchQuery &&
          !searchError && (
            <div className="text-center py-8">
              <div className="text-4xl mb-2">🔍</div>
              <h3 className="font-medium mb-1">No results found</h3>
              <p className="text-sm text-muted-foreground">
                Try different keywords or ask more specific questions about your
                code.
              </p>
            </div>
          )}

        {/* Loading State */}
        {isSearching && (
          <div className="py-8">
            <LoadingSpinner text="Searching your codebase..." />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
