import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/** null: the page sets its own title (the repository page names the repository) */
const getPageTitle = (pathname: string): string | null => {
  const baseTitle = "CodeSage";

  switch (pathname) {
    case "/":
      return `${baseTitle} - AI-Powered Code Discovery`;
    case "/dashboard":
      return `${baseTitle} - Dashboard`;
    default:
      if (pathname.startsWith("/repository/")) {
        const [, , id, page] = pathname.split("/");
        return page === "file" ? `${baseTitle} - File in repository ${id}` : null;
      }
      return baseTitle;
  }
};

export const usePageTitle = () => {
  const location = useLocation();

  useEffect(() => {
    const title = getPageTitle(location.pathname);
    if (title) document.title = title;
  }, [location.pathname]);

  return getPageTitle(location.pathname);
};
