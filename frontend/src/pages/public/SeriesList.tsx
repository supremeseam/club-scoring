import { Badge, Group, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";
import { useGet, type S } from "../../api/client";
import { Query } from "../../components/bits";
import { Hero } from "../../components/Brand";

export default function SeriesList() {
  const q = useGet<S["SeriesSummary"][]>("/series");
  return (
    <>
      <Hero />
      <Stack className="page" gap="xl">
        <Query q={q}>
          {(list) => {
            if (!list.length) return <Text c="dimmed">No series published yet.</Text>;
            const seasons = [...new Set(list.map((s) => s.season))].sort((a, b) => b - a);
            return (
              <>
                {seasons.map((season) => (
                  <Stack key={season} gap="sm">
                    <Title order={2} className="section-title">{season} season</Title>
                    <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="md">
                      {list.filter((s) => s.season === season).map((s) => (
                        <Link key={s.id} className="series-card" to={s.race_id ? `/races/${s.race_id}` : `/series/${s.id}`}>
                          <Group justify="space-between" wrap="nowrap" align="flex-start">
                            <span className="title">{s.name}</span>
                            <Badge variant="light" color={s.kind === "single" ? "grape" : s.status === "complete" ? "gray" : undefined}>
                              {s.kind === "single" ? "single race" : s.status}
                            </Badge>
                          </Group>
                          {s.description && <Text size="sm" c="dimmed" mt={6} lineClamp={2}>{s.description}</Text>}
                          <Text size="xs" mt={10} fw={600} c="dimmed" tt="uppercase" style={{ letterSpacing: "0.06em" }}>
                            {s.kind === "single" ? "Single race" : `${s.race_count} ${s.race_count === 1 ? "race" : "races"} sailed`}
                          </Text>
                        </Link>
                      ))}
                    </SimpleGrid>
                  </Stack>
                ))}
              </>
            );
          }}
        </Query>
      </Stack>
    </>
  );
}
