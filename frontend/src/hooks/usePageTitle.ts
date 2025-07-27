import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const getPageTitle = (pathname: string): string => {
  const baseTitle = "CodeSage";

  switch (pathname) {
    case "/":
      return `${baseTitle} - AI-Powered Code Discovery`;
    case "/dashboard":
      return `${baseTitle} - Dashboard`;
    case "/repository":
      return `${baseTitle} - Repository`;
    default:
      if (pathname.startsWith("/repository/")) {
        const id = pathname.split("/")[2];
        return `${baseTitle} - Repository ${id}`;
      }
      return baseTitle;
  }
};

export const usePageTitle = () => {
  const location = useLocation();

  useEffect(() => {
    const title = getPageTitle(location.pathname);
    document.title = title;
  }, [location.pathname]);

  return getPageTitle(location.pathname);
};
