import { Badge, Button, Card, Group, Stack, Text, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, useGet } from "../../api/client";
import { Query, toastError } from "../../components/bits";
import { STATUS_COLOR, type SignupStatus } from "../../lib/crew";

export default function MySignups() {
  const q = useGet<SignupStatus[]>("/crew/my/signups");
  const qc = useQueryClient();
  const withdraw = async (id: number) => {
    try {
      await api(`/crew/my/signups/${id}/withdraw`, { method: "POST" });
      await qc.invalidateQueries({ queryKey: ["/crew/my/signups"] });
    } catch (e) { toastError(e); }
  };
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>My crew sign-ups</Title>
        <Button component={Link} to="/crew" variant="light">Crew board</Button>
      </Group>
      <Query q={q}>
        {(rows) => rows.length === 0 ? <Text c="dimmed">You have not signed up for anything yet.</Text> : (
          <Stack>
            {rows.map((s) => (
              <Card key={s.id} withBorder>
                <Group justify="space-between" wrap="nowrap" align="flex-start">
                  <div>
                    <Group gap="xs">
                      <Text fw={600}>{s.boat || "Any boat"}{s.race ? `, ${s.race}` : ""}</Text>
                      <Badge color={STATUS_COLOR[s.status]}>{s.status}</Badge>
                    </Group>
                    {s.skipper_contact && (
                      <Text size="sm">Skipper: {[s.skipper_contact.name, s.skipper_contact.email, s.skipper_contact.phone, s.skipper_contact.note].filter(Boolean).join(" - ")}</Text>
                    )}
                  </div>
                  {s.status !== "withdrawn" && <Button size="compact-sm" color="red" variant="light" onClick={() => withdraw(s.id)}>Withdraw</Button>}
                </Group>
              </Card>
            ))}
          </Stack>
        )}
      </Query>
    </Stack>
  );
}
