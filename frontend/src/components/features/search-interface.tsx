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
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Get search suggestions as user types
  useEffect(() => {
    const getSuggestions = async () => {
      if (searchQuery.length > 2 && canSearch) {
        try {
          const suggestions = await api.getSearchSuggestions(searchQuery);
          setSuggestions(suggestions.slice(0, 5));
          setShowSuggestions(true);
        } catch (error) {
          console.error("Error getting suggestions:", error);
        }
      } else {
        setSuggestions([]);
        setShowSuggestions(false);
      }
    };

    const timeoutId = setTimeout(getSuggestions, 300); // Debounce
    return () => clearTimeout(timeoutId);
  }, [searchQuery, canSearch]);

  const handleSearch = async (query?: string) => {
    const queryToSearch = query || searchQuery;
    if (!queryToSearch.trim() || !canSearch) return;

    setIsSearching(true);
    setShowSuggestions(false);

    try {
      const results = await api.searchCode({
        query: queryToSearch,
        repository_id: repositoryId,
        per_page: 10,
      });
      setSearchResults(results.hits || []);
      if (query) {
        setSearchQuery(query);
      }
    } catch (error) {
      console.error("Search error:", error);
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch();
  };

  const handleSuggestionClick = (suggestion: string) => {
    handleSearch(suggestion);
    searchInputRef.current?.focus();
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
              </div>
              <Button
                type="submit"
                disabled={!canSearch || isSearching || !searchQuery.trim()}
              >
                {isSearching ? "Searching..." : "Search"}
              </Button>
            </div>
          </form>
        </div>

        {/* Loading State */}
        {isSearching && (
          <div className="py-8">
            <LoadingSpinner text="Searching your codebase..." />
          </div>
        )}

        {/* Search Results */}
        {!isSearching && searchResults.length > 0 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Search Results</h3>
              <span className="text-sm text-muted-foreground">
                {searchResults.length} result
                {searchResults.length !== 1 ? "s" : ""}
              </span>
            </div>

            {searchResults.map((result, index) => (
              <Card
                key={result.id || index}
                className="hover:shadow-md transition-shadow"
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <h4 className="font-medium text-lg">{result.title}</h4>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded">
                        Score: {result.score.toFixed(2)}
                      </span>
                      {result.entity_type && (
                        <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded">
                          {result.entity_type}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="mb-3">
                    <p className="text-sm text-muted-foreground">
                      {result.summary || result.content}
                    </p>
                  </div>

                  <div className="flex items-center justify-between text-xs border-t pt-2">
                    <div className="flex items-center gap-2">
                      <span className="text-blue-600 font-medium">
                        {result.file_path}
                      </span>
                      {result.line_number && (
                        <span className="text-muted-foreground">
                          Line {result.line_number}
                        </span>
                      )}
                    </div>
                    {result.language && (
                      <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded">
                        {result.language}
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* No Results */}
        {!isSearching && searchQuery && searchResults.length === 0 && (
          <div className="text-center py-8">
            <div className="text-2xl mb-2">🔍</div>
            <p className="text-muted-foreground">
              No results found for "{searchQuery}"
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Try different keywords or ask a more specific question
            </p>
          </div>
        )}

        {/* Disabled State */}
        {!canSearch && (
          <div className="text-center py-8 bg-muted/50 rounded-lg">
            <div className="text-2xl mb-2">⏳</div>
            <p className="text-muted-foreground">
              Search will be available once repository processing is complete
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
