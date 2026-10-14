import { Alert, Anchor, Badge, Button, Card, Code, CopyButton, Group, Modal, Select, SimpleGrid, Stack, Text, Textarea, TextInput, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, useGet } from "../../api/client";
import { useAuth } from "../../auth";
import { Query, toastError, toastOk } from "../../components/bits";
import { saveToken, STATUS_COLOR, type Board, type Options, type Posting, type SignupStatus } from "../../lib/crew";

type Target = { posting_id?: number; boat_id?: number; race_id?: number; label: string };

function SignupModal({ target, onClose }: { target: Target; onClose: () => void }) {
  const { user } = useAuth();
  const opts = useGet<Options>("/crew/options");
  const qc = useQueryClient();
  const [boat, setBoat] = useState<string | null>(target.boat_id ? String(target.boat_id) : null);
  const [race, setRace] = useState<string | null>(target.race_id ? String(target.race_id) : null);
  const [f, setF] = useState({ name: "", email: "", phone: "", experience: "", message: "", website: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ token: string } | null>(null);
  const [error, setError] = useState("");
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.currentTarget.value });
  const locked = !!target.posting_id;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/csrf");
      const r = await api<{ token: string }>("/crew/signups", {
        method: "POST",
        body: { ...f, posting_id: target.posting_id ?? null, boat_id: boat ? Number(boat) : null, race_id: race ? Number(race) : null },
      });
      if (r.token) saveToken(r.token);
      setDone(r);
      await qc.invalidateQueries({ queryKey: ["/crew/board"] });
      await qc.invalidateQueries({ queryKey: ["/crew/my/signups"] });
    } catch (ex) {
      setError(ex instanceof Error ? ex.message : "Could not send");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal opened onClose={onClose} title={`Crew sign-up: ${target.label}`} size="lg">
      {done ? (
        <Stack>
          <Alert color="green" title="Request sent">
            The skipper or race committee will see it when they sign in. Come back to this page to check the answer;
            this browser remembers your request{user ? ", and it is listed under My crew sign-ups" : ""}.
          </Alert>
          {done.token && !user && (
            <>
              <Text size="sm">Want to check from another device? Keep this private code. Anyone with it can see or cancel the request.</Text>
              <Group><Code>{done.token}</Code><CopyButton value={done.token}>{({ copy, copied }) => <Button size="compact-sm" variant="light" onClick={copy}>{copied ? "Copied" : "Copy"}</Button>}</CopyButton></Group>
            </>
          )}
          <Button onClick={onClose}>Done</Button>
        </Stack>
      ) : (
        <form onSubmit={submit}>
          <Stack>
            {error && <Alert color="red">{error}</Alert>}
            {!locked && (
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <Select label="Boat" description="Leave empty to offer to crew on any boat" clearable searchable value={boat} onChange={setBoat}
                  data={(opts.data?.boats ?? []).map((b) => ({ value: String(b.id), label: `${b.name} (${b.sail_number})` }))} />
                <Select label="Race" description="Leave empty for any race" clearable value={race} onChange={setRace}
                  data={(opts.data?.races ?? []).map((r) => ({ value: String(r.id), label: r.label }))} />
              </SimpleGrid>
            )}
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <TextInput label="Your name" required maxLength={80} value={f.name} onChange={set("name")} />
              <TextInput label="Email" type="email" required maxLength={254} value={f.email} onChange={set("email")} />
              <TextInput label="Phone (optional)" maxLength={30} value={f.phone} onChange={set("phone")} />
              <TextInput label="Experience" description="e.g. dinghy racing, 3 seasons on spinnaker" maxLength={200} value={f.experience} onChange={set("experience")} />
            </SimpleGrid>
            <Textarea label="Message to the skipper (optional)" maxLength={500} autosize minRows={2} value={f.message} onChange={set("message")} />
            {/* honeypot: hidden from people, irresistible to form-filling bots */}
            <div style={{ position: "absolute", left: "-9999px" }} aria-hidden="true">
              <label>Website<input tabIndex={-1} autoComplete="off" value={f.website} onChange={set("website")} /></label>
            </div>
            <Text size="xs" c="dimmed">Your name, email and phone are shown only to that boat's skipper and the race committee, never on the public page.</Text>
            <Button type="submit" loading={busy}>Send request</Button>
          </Stack>
        </form>
      )}
    </Modal>
  );
}

/** A signed-in crew account's own sign-ups (no one else sees this box). */
function MyRequests() {
  const q = useGet<SignupStatus[]>("/crew/my/signups");
  const qc = useQueryClient();
  const withdraw = async (id: number) => {
    try {
      await api(`/crew/my/signups/${id}/withdraw`, { method: "POST" });
      toastOk("Request withdrawn");
      await qc.invalidateQueries({ queryKey: ["/crew/my/signups"] });
      await qc.invalidateQueries({ queryKey: ["/crew/board"] });
    } catch (e) { toastError(e); }
  };
  const rows = (q.data ?? []).filter((s) => s.status !== "withdrawn");
  if (!rows.length) return null;
  return (
    <Card withBorder>
      <Title order={4} mb="xs">Your requests</Title>
      <Stack gap="xs">
        {rows.map((s) => (
          <Group key={s.id} justify="space-between" wrap="nowrap" align="flex-start">
            <div>
              <Group gap="xs">
                <Text fw={600}>{s.boat || "Any boat"}{s.race ? `, ${s.race}` : ""}</Text>
                <Badge color={STATUS_COLOR[s.status]}>{s.status}</Badge>
              </Group>
              {s.skipper_contact && (
                <Text size="sm">Skipper: {[s.skipper_contact.name, s.skipper_contact.email, s.skipper_contact.phone, s.skipper_contact.note].filter(Boolean).join(" - ")}</Text>
              )}
            </div>
            <Button size="compact-sm" variant="light" color="red" onClick={() => withdraw(s.id)}>Withdraw</Button>
          </Group>
        ))}
      </Stack>
    </Card>
  );
}

function PostingLine({ p, onJoin }: { p: Posting; onJoin: () => void }) {
  return (
    <Group justify="space-between" wrap="nowrap" align="flex-start">
      <div>
        <Group gap="xs">
          <Text fw={600} size="sm">{p.role || "Crew"}{p.spots > 1 ? ` (${p.spots} spots)` : ""}</Text>
          <Badge variant="light" color={p.race_id ? "blue" : "gray"}>{p.race || "Any race"}</Badge>
          {!!p.interested && <Badge variant="outline" color="yellow">{p.interested} interested</Badge>}
        </Group>
        {p.experience && <Text size="sm" c="dimmed">Wanted: {p.experience}</Text>}
        {p.notes && <Text size="sm">{p.notes}</Text>}
      </div>
      <Button size="compact-sm" onClick={onJoin}>I'm in</Button>
    </Group>
  );
}

export default function CrewBoard() {
  const board = useGet<Board>("/crew/board");
  const { user } = useAuth();
  const [target, setTarget] = useState<Target | null>(null);
  return (
    <Stack>
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={2}>Crew board</Title>
          <Text c="dimmed">Boats that need crew, and races where sailors have offered to sail.</Text>
        </div>
        <Group gap="xs">
          <Button onClick={() => setTarget({ label: "any boat or race" })}>Offer to crew</Button>
          {user?.role === "crew" && <Button component={Link} to="/crew/my" variant="light">My sign-ups</Button>}
          {!user && <Button component={Link} to="/crew/join" variant="default">Skipper or crew account</Button>}
        </Group>
      </Group>
      {user?.role === "crew" && <MyRequests />}
      <Query q={board}>
        {(b) => (
          <>
            <Title order={4}>Boats looking for crew</Title>
            {b.boats.length === 0 && <Text c="dimmed">No boat has posted an opening right now. You can still offer to crew above.</Text>}
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              {b.boats.map((boat) => (
                <Card key={boat.boat_id} withBorder>
                  <Group justify="space-between" mb={4}>
                    <Anchor component={Link} to={`/boats/${boat.boat_id}`} fw={700}>{boat.name}</Anchor>
                    <Text size="sm" c="dimmed">{boat.sail_number}{boat.design ? ` - ${boat.design}` : ""}{boat.fleet ? ` - ${boat.fleet}` : ""}</Text>
                  </Group>
                  {boat.notes && <Text size="sm" mb="xs">{boat.notes}</Text>}
                  <Stack gap="sm">
                    {boat.postings.map((p) => (
                      <PostingLine key={p.id} p={p} onJoin={() => setTarget({ posting_id: p.id, boat_id: boat.boat_id, race_id: p.race_id ?? undefined, label: boat.name })} />
                    ))}
                  </Stack>
                  <Button mt="sm" size="compact-sm" variant="subtle" onClick={() => setTarget({ boat_id: boat.boat_id, label: boat.name })}>
                    Sign up for this boat in general
                  </Button>
                </Card>
              ))}
            </SimpleGrid>
            {b.open_to_any > 0 && <Text size="sm" c="dimmed">{b.open_to_any} sailor{b.open_to_any === 1 ? " is" : "s are"} open to crewing on any boat, any race.</Text>}
            <Title order={4} mt="md">Upcoming races</Title>
            {b.races.length === 0 && <Text c="dimmed">No upcoming races are scheduled.</Text>}
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              {b.races.map((r) => (
                <Card key={r.race_id} withBorder>
                  <Group justify="space-between">
                    <div>
                      <Text fw={600}>{r.label}</Text>
                      <Text size="sm" c="dimmed">{r.volunteers} sailor{r.volunteers === 1 ? "" : "s"} offering to crew</Text>
                    </div>
                    <Button size="compact-sm" variant="light" onClick={() => setTarget({ race_id: r.race_id, label: r.label })}>I can crew</Button>
                  </Group>
                </Card>
              ))}
            </SimpleGrid>
          </>
        )}
      </Query>
      {target && <SignupModal target={target} onClose={() => setTarget(null)} />}
    </Stack>
  );
}
