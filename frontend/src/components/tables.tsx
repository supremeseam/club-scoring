import { Anchor, Badge, Table, Text } from "@mantine/core";
import { Link } from "react-router-dom";
import type { S } from "../api/client";
import { fmtDate, fmtPoints } from "../lib/time";
import { Place } from "./Brand";

export function BoatLink({ boat }: { boat: S["PublicBoat"] }) {
  return (
    <Anchor component={Link} to={`/boats/${boat.id}`} size="sm">
      {boat.name}
    </Anchor>
  );
}

export function StatusBadge({ final }: { final: boolean }) {
  return <Badge color={final ? "green" : "yellow"}>{final ? "Final" : "Provisional"}</Badge>;
}

const MARK: Record<string, string> = { fallback: "†", manual: "‡" };

export function ResultsTable({ block, pursuit = false }: { block: S["FleetResults"]; pursuit?: boolean }) {
  return (
    <Table.ScrollContainer minWidth={720}>
      <Table striped highlightOnHover className="brand-table">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Pl</Table.Th>
            <Table.Th>Boat</Table.Th>
            <Table.Th>Sail #</Table.Th>
            <Table.Th>Skipper</Table.Th>
            <Table.Th>Club</Table.Th>
            <Table.Th ta="right">Rating ({block.rating_type})</Table.Th>
            <Table.Th ta="right">{pursuit ? "Own elapsed" : "Elapsed"}</Table.Th>
            <Table.Th ta="right">{pursuit ? "Since 1st gun" : "Corrected"}</Table.Th>
            <Table.Th ta="right">Pts</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {block.rows.map((r) => (
            <Table.Tr key={r.boat.id}>
              <Table.Td><Place place={r.place} /></Table.Td>
              <Table.Td><BoatLink boat={r.boat} /></Table.Td>
              <Table.Td>{r.boat.sail_number}</Table.Td>
              <Table.Td>{r.boat.skipper}</Table.Td>
              <Table.Td>{r.boat.home_club}</Table.Td>
              <Table.Td ta="right">
                {r.rating === null ? "" : r.rating}
                {r.rating_source ? MARK[r.rating_source] ?? "" : ""}
                {r.rating !== null && r.rating_type !== block.rating_type ? <Text span size="xs" c="dimmed"> {r.rating_type}</Text> : null}
              </Table.Td>
              <Table.Td ta="right">{r.elapsed ?? ""}</Table.Td>
              <Table.Td ta="right">{r.corrected ?? ""}</Table.Td>
              <Table.Td ta="right">
                {fmtPoints(r.points)}
                {r.code ? <Text span size="xs" c="dimmed" title={r.note || undefined}> {r.code}{r.note ? " *" : ""}</Text> : null}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

export function StandingsTable({ block }: { block: S["FleetStandings"] }) {
  return (
    <Table.ScrollContainer minWidth={500}>
      <Table striped highlightOnHover className="brand-table">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Rk</Table.Th>
            <Table.Th>Boat</Table.Th>
            <Table.Th>Sail #</Table.Th>
            {block.races.map((r) => (
              <Table.Th key={r.id} ta="right" title={r.date}>
                <Anchor component={Link} to={`/races/${r.id}`} size="sm">R{r.number}</Anchor>
                <Text size="xs" c="dimmed">{fmtDate(r.date)}</Text>
              </Table.Th>
            ))}
            <Table.Th ta="right">Total</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {block.standings.map((row) => (
            <Table.Tr key={row.boat.id} c={row.guest ? "dimmed" : undefined} fs={row.guest ? "italic" : undefined}>
              <Table.Td fw={600}>{row.guest ? `(${row.rank})` : <Place place={row.rank} />}</Table.Td>
              <Table.Td>
                <BoatLink boat={row.boat} />
                {row.guest ? <Badge size="xs" variant="light" ml={6}>Guest</Badge> : null}
              </Table.Td>
              <Table.Td>{row.boat.sail_number}</Table.Td>
              {row.scores.map((sc) => {
                const t = fmtPoints(sc.points);
                return (
                  <Table.Td key={sc.race_id} ta="right" c={sc.discarded ? "dimmed" : undefined}>
                    {sc.discarded ? `(${t})` : t}
                    {sc.code ? <Text span size="xs" c="dimmed"> {sc.code}</Text> : null}
                    {sc.average ? <Text span size="xs" c="dimmed"> avg</Text> : null}
                  </Table.Td>
                );
              })}
              <Table.Td ta="right" fw={700}>{fmtPoints(row.total)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
