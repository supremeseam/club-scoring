import { Badge, Button, Card, Checkbox, Group, NumberInput, Select, SimpleGrid, Stack, Tabs, Text, Textarea, TextInput, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, useGet } from "../../api/client";
import { useAuth } from "../../auth";
import { Query, toastError, toastOk } from "../../components/bits";
import { STATUS_COLOR, type CrewInfo, type Posting, type SignupFull, type SkipperOverview } from "../../lib/crew";

type BoatRow = SkipperOverview["boats"][number];
const EMPTY: Omit<Posting, "id" | "race"> = { race_id: null, role: "", spots: 1, experience: "", notes: "", is_open: true };

function InfoForm({ boat }: { boat: BoatRow }) {
  const qc = useQueryClient();
  const [v, setV] = useState<CrewInfo>(boat.info);
  const save = async () => {
    try {
      await api(`/crew/skipper/boats/${boat.id}/info`, { method: "PUT", body: v });
      toastOk("Saved");
      await qc.invalidateQueries({ queryKey: ["/crew/skipper/overview"] });
    } catch (e) { toastError(e); }
  };
  const set = (k: keyof CrewInfo) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setV({ ...v, [k]: e.currentTarget.value });
  return (
    <Stack gap="xs">
      <Textarea label="About your crew spot" description="Shown on the public crew board. e.g. relaxed Wednesday racing, beginners welcome" maxLength={500} autosize minRows={2} value={v.notes} onChange={set("notes")} />
      <Select label="How should accepted sailors reach you?" allowDeselect={false} value={v.contact_preference}
        onChange={(x) => setV({ ...v, contact_preference: (x ?? "app") as CrewInfo["contact_preference"] })}
        data={[{ value: "app", label: "Through this site (they see your reply here)" }, { value: "email", label: "Email" }, { value: "phone", label: "Phone / text" }]} />
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <TextInput label="Contact name" maxLength={80} value={v.contact_name} onChange={set("contact_name")} />
        <TextInput label="Contact email" maxLength={254} value={v.contact_email} onChange={set("contact_email")} />
        <TextInput label="Contact phone" maxLength={30} value={v.contact_phone} onChange={set("contact_phone")} />
      </SimpleGrid>
      <Text size="xs" c="dimmed">Contact details are shared only with sailors you accept, and only the option you choose above.</Text>
      <Group><Button onClick={save}>Save</Button></Group>
    </Stack>
  );
}

function PostingEditor({ boat, races }: { boat: BoatRow; races: SkipperOverview["races"] }) {
  const qc = useQueryClient();
  const [v, setV] = useState({ ...EMPTY });
  const refresh = () => qc.invalidateQueries({ queryKey: ["/crew/skipper/overview"] });
  const add = async () => {
    try {
      await api(`/crew/skipper/boats/${boat.id}/postings`, { method: "POST", body: v });
      setV({ ...EMPTY });
      await refresh();
    } catch (e) { toastError(e); }
  };
  const toggle = async (p: Posting) => {
    try {
      await api(`/crew/skipper/postings/${p.id}`, { method: "PUT", body: { race_id: p.race_id, role: p.role, spots: p.spots, experience: p.experience, notes: p.notes, is_open: !p.is_open } });
      await refresh();
    } catch (e) { toastError(e); }
  };
  const remove = async (p: Posting) => {
    try { await api(`/crew/skipper/postings/${p.id}`, { method: "DELETE" }); await refresh(); } catch (e) { toastError(e); }
  };
  return (
    <Stack gap="sm">
      {boat.postings.map((p) => (
        <Group key={p.id} justify="space-between" wrap="nowrap">
          <div>
            <Group gap="xs">
              <Text fw={600} size="sm">{p.role || "Crew"} x{p.spots}</Text>
              <Badge variant="light">{p.race || "Any race"}</Badge>
              <Badge color={p.is_open ? "green" : "gray"}>{p.is_open ? "open" : "closed"}</Badge>
            </Group>
            {(p.experience || p.notes) && <Text size="sm" c="dimmed">{[p.experience, p.notes].filter(Boolean).join(" - ")}</Text>}
          </div>
          <Group gap="xs" wrap="nowrap">
            <Button size="compact-sm" variant="light" onClick={() => toggle(p)}>{p.is_open ? "Close" : "Reopen"}</Button>
            <Button size="compact-sm" variant="subtle" color="red" onClick={() => remove(p)}>Delete</Button>
          </Group>
        </Group>
      ))}
      <Card withBorder>
        <Text fw={600} mb="xs">Add an opening</Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="For" clearable placeholder="Any race this season" value={v.race_id ? String(v.race_id) : null}
            onChange={(x) => setV({ ...v, race_id: x ? Number(x) : null })} data={races.map((r) => ({ value: String(r.id), label: r.label }))} />
          <TextInput label="Position" placeholder="Trimmer, bow, tactician..." maxLength={60} value={v.role} onChange={(e) => setV({ ...v, role: e.currentTarget.value })} />
          <NumberInput label="Spots" min={1} max={20} value={v.spots} onChange={(x) => setV({ ...v, spots: Number(x) || 1 })} />
          <TextInput label="Experience wanted" maxLength={120} value={v.experience} onChange={(e) => setV({ ...v, experience: e.currentTarget.value })} />
        </SimpleGrid>
        <Textarea mt="xs" label="Notes" maxLength={500} autosize minRows={1} value={v.notes} onChange={(e) => setV({ ...v, notes: e.currentTarget.value })} />
        <Button mt="sm" onClick={add}>Post opening</Button>
      </Card>
    </Stack>
  );
}

function Requests({ onSeen }: { onSeen: () => void }) {
  const q = useGet<SignupFull[]>("/crew/skipper/signups");
  const qc = useQueryClient();
  const [openOnly, setOpenOnly] = useState(true);
  const respond = async (id: number, status: string) => {
    try {
      await api(`/crew/skipper/signups/${id}/respond`, { method: "POST", body: { status } });
      await qc.invalidateQueries({ queryKey: ["/crew/skipper/signups"] });
      onSeen();
    } catch (e) { toastError(e); }
  };
  const markSeen = async () => {
    try { await api("/crew/skipper/signups/mark-seen", { method: "POST" }); await qc.invalidateQueries({ queryKey: ["/crew/skipper/signups"] }); onSeen(); } catch (e) { toastError(e); }
  };
  return (
    <Query q={q}>
      {(rows) => {
        const shown = rows.filter((r) => !openOnly || r.status === "pending" || r.status === "accepted");
        return (
          <Stack>
            <Group justify="space-between">
              <Checkbox label="Hide declined" checked={openOnly} onChange={(e) => setOpenOnly(e.currentTarget.checked)} />
              <Button size="compact-sm" variant="subtle" onClick={markSeen}>Mark all as seen</Button>
            </Group>
            {shown.length === 0 && <Text c="dimmed">No requests yet. They appear here, with a badge in the menu, when sailors sign up for your boat.</Text>}
            {shown.map((r) => (
              <Card key={r.id} withBorder>
                <Group justify="space-between" align="flex-start" wrap="nowrap">
                  <div>
                    <Group gap="xs">
                      <Text fw={700}>{r.name}</Text>
                      <Badge color={STATUS_COLOR[r.status]}>{r.status}</Badge>
                      {!r.seen && r.boat_id && <Badge color="red" variant="filled">new</Badge>}
                    </Group>
                    <Text size="sm">{r.boat ? `For ${r.boat}` : "Will crew on any boat"}{r.race ? `, ${r.race}` : ""}{r.role ? ` (${r.role})` : ""}</Text>
                    <Text size="sm" c="dimmed">{[r.email, r.phone].filter(Boolean).join(" - ")}</Text>
                    {r.experience && <Text size="sm">Experience: {r.experience}</Text>}
                    {r.message && <Text size="sm">"{r.message}"</Text>}
                  </div>
                  {r.boat_id && (
                    <Group gap="xs" wrap="nowrap">
                      <Button size="compact-sm" color="green" disabled={r.status === "accepted"} onClick={() => respond(r.id, "accepted")}>Accept</Button>
                      <Button size="compact-sm" variant="default" disabled={r.status === "declined"} onClick={() => respond(r.id, "declined")}>Decline</Button>
                    </Group>
                  )}
                </Group>
              </Card>
            ))}
          </Stack>
        );
      }}
    </Query>
  );
}

export default function SkipperHome() {
  const q = useGet<SkipperOverview>("/crew/skipper/overview");
  const { refresh } = useAuth();
  const qc = useQueryClient();
  const onSeen = () => { void refresh(); void qc.invalidateQueries({ queryKey: ["/crew/skipper/overview"] }); };
  const [tab, setTab] = useState<string | null>("requests");
  return (
    <Stack>
      <Title order={2}>My boat's crew</Title>
      <Text c="dimmed" size="sm">You can change crew openings and contact details here. Your boat's name, rating and results are managed by the race committee.</Text>
      <Query q={q}>
        {(o) => (
          <Tabs value={tab} onChange={setTab}>
            <Tabs.List>
              <Tabs.Tab value="requests" rightSection={o.unseen ? <Badge color="red" variant="filled" size="sm">{o.unseen}</Badge> : null}>Requests</Tabs.Tab>
              {o.boats.map((b) => <Tabs.Tab key={b.id} value={`boat-${b.id}`}>{b.name}</Tabs.Tab>)}
            </Tabs.List>
            <Tabs.Panel value="requests" pt="md"><Requests onSeen={onSeen} /></Tabs.Panel>
            {o.boats.map((b) => (
              <Tabs.Panel key={b.id} value={`boat-${b.id}`} pt="md">
                <Stack>
                  <Title order={4}>Openings</Title>
                  <PostingEditor boat={b} races={o.races} />
                  <Title order={4} mt="md">About and contact</Title>
                  <InfoForm boat={b} />
                </Stack>
              </Tabs.Panel>
            ))}
          </Tabs>
        )}
      </Query>
    </Stack>
  );
}
