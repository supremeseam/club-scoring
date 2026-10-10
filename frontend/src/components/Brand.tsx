import { Anchor, Text, Title } from "@mantine/core";
import { useGet, type SiteConfig } from "../api/client";

export const useSite = () => useGet<SiteConfig>("/config");

/** The club burgee on its own (header, tab, small spaces). Falls back to a plain pennant if none is set. */
export function Burgee({ height = 32, tile = false }: { height?: number; tile?: boolean }) {
  const { data } = useSite();
  const img = data?.burgee_url ? (
    <img className="burgee" src={data.burgee_url} alt="" height={height} />
  ) : (
    <svg className="burgee" viewBox="0 0 120 70" height={height} aria-hidden="true">
      <path d="M2 2 L118 35 L2 68 Z" fill="currentColor" />
      <path d="M2 40 q15 -8 30 0 t30 0 t30 0 L118 35 L2 68 Z" fill="#fff" opacity="0.25" />
    </svg>
  );
  return tile ? <span className="burgee-tile">{img}</span> : img;
}

/** Big banner for the home page: burgee tile, product name, club name, and a wave edge. */
export function Hero() {
  const { data } = useSite();
  return (
    <div className="hero">
      <div className="hero-inner">
        <Burgee height={72} tile />
        <div>
          <Title order={1} className="hero-title">{data?.app_name ?? "Race Results"}</Title>
          <Text className="hero-sub">
            {data?.club_name}
            {data?.tagline ? ` · ${data.tagline}` : ""}
          </Text>
        </div>
      </div>
      <svg className="hero-wave" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden="true">
        <path className="back" d="M0,30 C200,70 420,0 700,28 C980,56 1200,6 1440,34 L1440,80 L0,80 Z" />
        <path d="M0,46 C240,80 500,12 760,40 C1020,68 1230,26 1440,52 L1440,80 L0,80 Z" />
      </svg>
    </div>
  );
}

export function SiteFooter() {
  const { data } = useSite();
  return (
    <footer className="site-footer">
      <Burgee height={22} />
      <span>{data?.club_name}</span>
      {data?.website && <Anchor href={data.website} size="sm" target="_blank" rel="noopener noreferrer">{data.website.replace(/^https?:\/\//, "")}</Anchor>}
      <span style={{ marginLeft: "auto" }}>Open-source race scoring</span>
    </footer>
  );
}

/** Round gold/silver/bronze marker for places 1-3, plain text otherwise. */
export function Place({ place }: { place: number | null | undefined }) {
  if (place === null || place === undefined || place === 0) return <>{""}</>;
  return place <= 3 ? <span className={`medal medal-${place}`}>{place}</span> : <>{place}</>;
}
