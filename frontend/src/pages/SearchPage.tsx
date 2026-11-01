import { SearchInterface } from "@/components/features/search-interface";

/** Search across every indexed repository; each hit names and links to its own */
export function SearchPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        <SearchInterface canSearch />
      </div>
    </div>
  );
}
