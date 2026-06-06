export const GA_MEASUREMENT_ID = "G-RLK185VS4J";

type GtagCommand = "config" | "event" | "js";
type GtagParameters = Record<string, unknown>;

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (
      command: GtagCommand,
      targetId: string | Date,
      config?: GtagParameters,
    ) => void;
  }
}

function getGtag() {
  window.dataLayer = window.dataLayer || [];
  window.gtag =
    window.gtag ||
    ((command, targetId, config) => {
      window.dataLayer?.push([command, targetId, config]);
    });
  return window.gtag;
}

export function pageview(url: string) {
  getGtag()("config", GA_MEASUREMENT_ID, {
    page_path: url,
  });
}

export function trackEvent(
  action: string,
  parameters: GtagParameters = {},
) {
  getGtag()("event", action, parameters);
}
