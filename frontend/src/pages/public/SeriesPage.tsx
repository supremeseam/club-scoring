import { Alert, Anchor, Button, Group, Stack, Tabs, Text, Title } from "@mantine/core";
import { Link, useParams } from "react-router-dom";
import { useGet, type S } from "../../api/client";
import { Query } from "../../components/bits";
import { StandingsTable, StatusBadge } from "../../components/tables";
import { withBase } from "../../lib/base";
import { fmtDate } from "../../lib/time";

export default function SeriesPage() {
  const { id } = useParams();
  const st = useGet<S["SeriesStandings"]>(`/series/${id}/standings`);
  const detail = useGet<S["SeriesDetail"]>(`/series/${id}`);
  return (
    <Stack>
      <Query q={st}>
        {(data) => {
          const blocks = [...data.fleets, ...(data.combined ? [data.combined] : [])];
          return (
            <>
              <Group justify="space-between">
                <Title order={1}>{data.series.name} {data.series.season}</Title>
                <Group>
                  <Button component="a" href={withBase(`/api/series/${id}/standings.pdf`)} variant="default" size="xs">
                    Standings PDF
                  </Button>
                  <Button component="a" href={withBase(`/api/series/${id}/standings.csv`)} variant="default" size="xs">
                    CSV
                  </Button>
                </Group>
              </Group>
              <Text c="dimmed">{data.series.description}</Text>
              {data.warnings.map((w) => <Alert key={w} color="yellow">{w}</Alert>)}
              {blocks.length === 0 ? (
                <Text>No entries yet.</Text>
              ) : (
                <Tabs defaultValue={String(blocks[0].fleet_id ?? "overall")}>
                  <Tabs.List>
                    {blocks.map((b) => (
                      <Tabs.Tab key={b.fleet_name} value={String(b.fleet_id ?? "overall")}>{b.fleet_name}</Tabs.Tab>
                    ))}
                  </Tabs.List>
                  {blocks.map((b) => (
                    <Tabs.Panel key={b.fleet_name} value={String(b.fleet_id ?? "overall")} pt="sm">
                      {b.races.length ? <StandingsTable block={b} /> : <Text>No races scored yet.</Text>}
                      <Text size="xs" c="dimmed" mt="xs">
                        Discarded scores in parentheses. avg = scored by average (RC duty / redress). Guests (italic) are scored as if entered; (n) is where they would rank and never changes a series boat’s rank.
                      </Text>
                    </Tabs.Panel>
                  ))}
                </Tabs>
              )}
            </>
          );
        }}
      </Query>
      <Title order={3} className="section-title">Races</Title>
      <Query q={detail}>
        {(d) => (
          <Stack gap={4}>
            {d.races.map((r) => (
              <Group key={r.id} gap="sm">
                <Anchor component={Link} to={`/races/${r.id}`}>Race {r.number}</Anchor>
                <Text size="sm">{fmtDate(r.date)}</Text>
                {r.status === "sailed" ? <StatusBadge final={r.final} /> : <Text size="sm" c="dimmed">{r.status}</Text>}
              </Group>
            ))}
          </Stack>
        )}
      </Query>
    </Stack>
  );
}
