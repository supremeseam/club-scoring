import { Alert, Anchor, Button, Group, Stack, Text, Title } from "@mantine/core";
import { Link, useParams } from "react-router-dom";
import { useGet, type S } from "../../api/client";
import { Query } from "../../components/bits";
import { Podium } from "../../components/Podium";
import { ResultsTable, StatusBadge } from "../../components/tables";
import { fmtDate } from "../../lib/time";

export default function RacePage() {
  const { id } = useParams();
  const q = useGet<S["RaceResults"]>(`/races/${id}/results`);
  return (
    <Query q={q}>
      {(r) => (
        <Stack>
          <Group justify="space-between">
            <div>
              <Title order={1}>Race {r.number}</Title>
              <Anchor component={Link} to={`/series/${r.series_id}`}>{r.series_name}</Anchor>
              <Text size="sm">{fmtDate(r.date)}</Text>
            </div>
            <Stack gap={4} align="flex-end">
              {r.status === "abandoned" ? <Text c="red" fw={600}>Abandoned</Text> : <StatusBadge final={r.final} />}
              <Group>
                <Button component="a" href={`/api/races/${id}/podium.pdf`} variant="filled" size="xs">
                  Print podium sheet
                </Button>
                <Button component="a" href={`/api/races/${id}/results.csv`} variant="default" size="xs">
                  CSV
                </Button>
              </Group>
            </Stack>
          </Group>
          {r.protests_pending > 0 && (
            <Alert color="yellow" title="Protest pending">
              {r.protests_pending === 1 ? "A protest is" : `${r.protests_pending} protests are`} pending for this race. Results may change.
            </Alert>
          )}
          {r.fleets.map((b) => (
            <Stack key={b.fleet_id} gap="xs">
              <Title order={3} className="section-title">
                {b.fleet_name}
                <Text span size="sm" c="dimmed"> {b.course ?? ""}{b.distance_nm ? `, ${Number(b.distance_nm).toFixed(2)} nm` : ""}</Text>
              </Title>
              <Podium block={b} />
              <ResultsTable block={b} pursuit={r.is_pursuit} />
              {b.rows.some((x) => x.note) && (
                <Stack gap={2}>
                  <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: "0.06em" }}>Penalties &amp; notes</Text>
                  {b.rows.filter((x) => x.note).map((x) => (
                    <Text key={x.boat.id} size="sm"><b>{x.boat.name}</b> ({x.code ?? x.status}): {x.note}</Text>
                  ))}
                </Stack>
              )}
            </Stack>
          ))}
          <Text size="xs" c="dimmed">
            {"†"} fallback rating used {"‡"} rating entered manually by race committee.
            {r.final ? "" : " Results are provisional and subject to protest."}
          </Text>
        </Stack>
      )}
    </Query>
  );
}
