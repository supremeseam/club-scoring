import "@fontsource-variable/inter";
import "@fontsource-variable/source-serif-4";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./styles.css";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { api, type SiteConfig } from "./api/client";
import { AuthProvider } from "./auth";
import { makeTheme } from "./theme";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });

/** Club branding comes from the server's environment, so one build fits any club. */
function Themed({ children }: { children: React.ReactNode }) {
  const cfg = useQuery({ queryKey: ["/config"], queryFn: () => api<SiteConfig>("/config") });
  const theme = React.useMemo(() => makeTheme(cfg.data), [cfg.data]);
  React.useEffect(() => {
    const c = cfg.data;
    if (!c) return;
    document.title = c.app_name || c.club_short_name || c.club_name;
    if (c.burgee_url) {
      let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
      if (!link) {
        link = document.createElement("link");
        link.rel = "icon";
        document.head.appendChild(link);
      }
      link.href = c.burgee_url;
    }
    if (c.brand_hex) document.querySelector('meta[name="theme-color"]')?.setAttribute("content", c.brand_hex);
  }, [cfg.data]);
  return (
    <MantineProvider defaultColorScheme="auto" theme={theme}>
      {children}
    </MantineProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <Themed>
        <Notifications position="top-center" />
        <AuthProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AuthProvider>
      </Themed>
    </QueryClientProvider>
  </React.StrictMode>,
);
