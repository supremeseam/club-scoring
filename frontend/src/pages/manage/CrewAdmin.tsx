import { Badge, Button, Card, Group, MultiSelect, PasswordInput, Select, Stack, Table, Tabs, Text, TextInput, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, useGet, type S } from "../../api/client";
import { useSite } from "../../components/Brand";
import { Query, toastError, toastOk } from "../../components/bits";
import { STATUS_COLOR, type SignupFull, type SkipperAccount, type SkipperRequestRow } from "../../lib/crew";

type BoatOpt = { value: string; label: string };

function useBoatOptions(): BoatOpt[] {
  const boats = useGet<S["BoatOut"][]>("/manage/boats");
  return (boats.data ?? []).map((b) => ({ value: String(b.id), label: `${b.name} (${b.sail_number})` }));
}

function CreateSkipper({ boats, request, onDone }: { boats: BoatOpt[]; request?: SkipperRequestRow; onDone: () => void }) {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [ids, setIds] = useState<string[]>(request?.boat_id ? [String(request.boat_id)] : []);
  const [name, setName] = useState(request?.name ?? "");
  const [email, setEmail] = useState(request?.email ?? "");
  const submit = async () => {
    try {
      const body = { username, password, boat_ids: ids.map(Number), name, email };
      await api(request ? `/manage/crew/skipper-requests/${request.id}/approve` : "/manage/crew/skippers", { method: "POST", body });
      toastOk(`Created ${username}. Give them the temporary password; they choose their own at first sign-in.`);
      onDone();
    } catch (e) { toastError(e); }
  };
  return (
    <Stack gap="xs">
      {!request && (
        <Group grow>
          <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <TextInput label="Email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
        </Group>
      )}
      <Group grow align="flex-end">
        <TextInput label="Username" value={username} onChange={(e) => setU(e.currentTarget.value)} />
        <PasswordInput label="Temporary password" description="15+ characters" value={password} onChange={(e) => setP(e.currentTarget.value)} />
      </Group>
      <MultiSelect label="Boats this skipper may manage crew for" searchable data={boats} value={ids} onChange={setIds}
        description="Crew info only: they can never change results, ratings or payments." />
      <Group><Button onClick={submit} disabled={!username || !password || ids.length === 0}>{request ? "Approve and create login" : "Create skipper login"}</Button></Group>
    </Stack>
  );
}

export default function CrewAdmin() {
  const boats = useBoatOptions();
  const cognito = useSite().data?.auth_mode === "cognito";
  const skippers = useGet<SkipperAccount[]>("/manage/crew/skippers");
  const requests = useGet<SkipperRequestRow[]>("/manage/crew/skipper-requests");
  const signups = useGet<SignupFull[]>("/manage/crew/signups");
  const qc = useQueryClient();
  const [tab, setTab] = useState<string | null>(null);      // null until chosen: the first tab depends on the sign-in mode
  const [approving, setApproving] = useState<number | null>(null);
  const [addBoat, setAddBoat] = useState<Record<number, string | null>>({});
  const reload = () => Promise.all(["skippers", "skipper-requests", "signups"].map((k) => qc.invalidateQueries({ queryKey: [`/manage/crew/${k}`] })));
  const link = async (path: string, user_id: number, boat_id: number) => {
    try { await api(`/manage/crew/skippers/${path}`, { method: "POST", body: { user_id, boat_id } }); await reload(); } catch (e) { toastError(e); }
  };
  const reject = async (id: number) => {
    try { await api(`/manage/crew/skipper-requests/${id}/reject`, { method: "POST" }); await reload(); } catch (e) { toastError(e); }
  };
  const removeSignup = async (id: number) => {
    try { await api(`/manage/crew/signups/${id}`, { method: "DELETE" }); await reload(); } catch (e) { toastError(e); }
  };
  return (
    <Stack>
      <Title order={2}>Crew board</Title>
      <Tabs value={tab ?? (cognito ? "skippers" : "requests")} onChange={setTab}>
        <Tabs.List>
          {!cognito && <Tabs.Tab value="requests" rightSection={requests.data?.length ? <Badge color="red" variant="filled" size="sm">{requests.data.length}</Badge> : null}>Login requests</Tabs.Tab>}
          <Tabs.Tab value="skippers">{cognito ? "Boat links" : "Skipper logins"}</Tabs.Tab>
          <Tabs.Tab value="signups">Sign-ups</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="requests" pt="md">
          <Query q={requests}>
            {(rows) => rows.length === 0 ? <Text c="dimmed">No skipper is waiting for a login.</Text> : (
              <Stack>
                {rows.map((r) => (
                  <Card key={r.id} withBorder>
                    <Group justify="space-between" align="flex-start">
                      <div>
                        <Text fw={700}>{r.name} <Text span c="dimmed" fw={400}>{r.email}</Text></Text>
                        <Text size="sm">Boat: {r.boat || "(not named)"}</Text>
                        {r.message && <Text size="sm" c="dimmed">{r.message}</Text>}
                      </div>
                      <Group gap="xs">
                        <Button size="compact-sm" onClick={() => setApproving(approving === r.id ? null : r.id)}>Approve</Button>
                        <Button size="compact-sm" variant="default" onClick={() => reject(r.id)}>Reject</Button>
                      </Group>
                    </Group>
                    {approving === r.id && <div style={{ marginTop: 12 }}><CreateSkipper boats={boats} request={r} onDone={() => { setApproving(null); void reload(); }} /></div>}
                  </Card>
                ))}
              </Stack>
            )}
          </Query>
        </Tabs.Panel>
        <Tabs.Panel value="skippers" pt="md">
          <Stack>
            <Query q={skippers}>
              {(rows) => (
                <Table withTableBorder>
                  <Table.Thead><Table.Tr><Table.Th>Login</Table.Th><Table.Th>Boats</Table.Th><Table.Th>Link another boat</Table.Th></Table.Tr></Table.Thead>
                  <Table.Tbody>
                    {rows.map((u) => (
                      <Table.Tr key={u.user_id}>
                        <Table.Td>{u.external ? (u.name || u.email || u.username) : u.username}<Text size="xs" c="dimmed">{u.external ? u.email : `${u.name} ${u.email}`}</Text>{u.role === "rc" && <Badge color="indigo" variant="light">committee</Badge>}{!u.active && <Badge color="gray">disabled</Badge>}</Table.Td>
                        <Table.Td>
                          <Group gap={4}>
                            {u.boats.map((b) => (
                              <Badge key={b.id} variant="light" rightSection={<span style={{ cursor: "pointer" }} onClick={() => link("unlink", u.user_id, b.id)}>x</span>}>{b.name}</Badge>
                            ))}
                          </Group>
                        </Table.Td>
                        <Table.Td>
                          <Group gap="xs" wrap="nowrap">
                            <Select size="xs" searchable placeholder="Boat" data={boats} value={addBoat[u.user_id] ?? null} onChange={(v) => setAddBoat({ ...addBoat, [u.user_id]: v })} />
                            <Button size="compact-xs" disabled={!addBoat[u.user_id]} onClick={() => link("link", u.user_id, Number(addBoat[u.user_id]))}>Link</Button>
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Query>
            {!cognito && <Card withBorder><Title order={5} mb="xs">New skipper login</Title><CreateSkipper boats={boats} onDone={() => void reload()} /></Card>}
            <Text size="xs" c="dimmed">{cognito && "People appear here after they first sign in. Link a boat to someone to let them manage its crew. "}Race committee accounts are listed too: link a boat to one and that person manages its crew under "My boat's crew", still with their committee access. To reset a password or disable a login, use the site admin, as for any account.</Text>
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="signups" pt="md">
          <Query q={signups}>
            {(rows) => (
              <Table withTableBorder>
                <Table.Thead><Table.Tr><Table.Th>Sailor</Table.Th><Table.Th>Wants</Table.Th><Table.Th>Status</Table.Th><Table.Th /></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {rows.map((r) => (
                    <Table.Tr key={r.id}>
                      <Table.Td>{r.name}<Text size="xs" c="dimmed">{[r.email, r.phone].filter(Boolean).join(" - ")}</Text></Table.Td>
                      <Table.Td>{r.boat || "Any boat"}{r.race ? `, ${r.race}` : ""}</Table.Td>
                      <Table.Td><Badge color={STATUS_COLOR[r.status]}>{r.status}</Badge></Table.Td>
                      <Table.Td><Button size="compact-xs" color="red" variant="subtle" onClick={() => removeSignup(r.id)}>Delete</Button></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Query>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
