import { Badge, Button, Card, Group, Modal, MultiSelect, Select, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, useGet, type S } from "../api/client";
import { RULE_SUGGESTIONS } from "../lib/penalties";
import { Query, toastError, toastOk } from "./bits";

type Protest = S["ProtestOut"];
const STATUS_COLOR: Record<string, string> = { filed: "orange", heard: "yellow", decided: "teal", withdrawn: "gray" };

/** Editor-only protest log for a race. The public sees only a "protest pending" notice. */
export function Protests({ raceId, boats }: { raceId: number; boats: S["BoatOut"][] }) {
  const q = useGet<Protest[]>(`/manage/races/${raceId}/protests`);
  const [editing, setEditing] = useState<Protest | "new" | null>(null);
  return (
    <Card withBorder padding="sm">
      <Stack gap="xs">
        <Group justify="space-between">
          <Text fw={600}>Protests &amp; redress</Text>
          <Button size="compact-sm" variant="light" onClick={() => setEditing("new")}>File a protest</Button>
        </Group>
        <Text size="xs" c="dimmed">
          Details are visible to editors only. The public sees "protest pending" while one is open, and the
          reason on any penalty you note on a finish. Results can't be marked final while a protest is pending.
        </Text>
        <Query q={q}>
          {(list) => list.length === 0 ? <Text size="sm" c="dimmed">No protests.</Text> : (
            <Stack gap={6}>
              {list.map((p) => (
                <Group key={p.id} justify="space-between" wrap="nowrap" align="flex-start" p="xs"
                  style={{ border: "1px solid var(--mantine-color-default-border)", borderRadius: 8 }}>
                  <div>
                    <Text size="sm" fw={600}>{p.protestor} v {p.protestees.join(", ") || "—"}</Text>
                    <Text size="xs" c="dimmed">{p.filed_on}{p.rules ? ` · ${p.rules}` : ""}</Text>
                    {p.decision && <Text size="sm" mt={4}>{p.decision}</Text>}
                  </div>
                  <Group gap={6} wrap="nowrap">
                    <Badge color={STATUS_COLOR[p.status]}>{p.status}</Badge>
                    <Button size="compact-xs" variant="default" onClick={() => setEditing(p)}>Edit</Button>
                  </Group>
                </Group>
              ))}
            </Stack>
          )}
        </Query>
      </Stack>
      {editing && <ProtestForm raceId={raceId} protest={editing === "new" ? null : editing} boats={boats} onClose={() => setEditing(null)} />}
    </Card>
  );
}

function ProtestForm({ raceId, protest, boats, onClose }: {
  raceId: number; protest: Protest | null; boats: S["BoatOut"][]; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [protestor, setProtestor] = useState<string | null>(protest?.protestor_id ? String(protest.protestor_id) : null);
  const [protestees, setProtestees] = useState<string[]>((protest?.protestee_ids ?? []).map(String));
  const [rules, setRules] = useState(protest?.rules ?? "");
  const [status, setStatus] = useState(protest?.status ?? "filed");
  const [decision, setDecision] = useState(protest?.decision ?? "");
  const [filedOn, setFiledOn] = useState(protest?.filed_on ?? new Date().toISOString().slice(0, 10));
  const options = boats.map((b) => ({ value: String(b.id), label: `${b.name} (${b.sail_number})` }));

  const save = async () => {
    const body = {
      filed_on: filedOn, protestor_id: protestor ? Number(protestor) : null,
      protestee_ids: protestees.map(Number), rules, status, decision,
    };
    try {
      await api(protest ? `/manage/protests/${protest.id}` : `/manage/races/${raceId}/protests`, { method: protest ? "PUT" : "POST", body });
      toastOk("Protest saved");
      await qc.invalidateQueries({ predicate: (k) => String(k.queryKey[0]).startsWith("/manage/") });
      onClose();
    } catch (e) { toastError(e); }
  };
  const remove = async () => {
    if (!protest) return;
    try {
      await api(`/manage/protests/${protest.id}`, { method: "DELETE" });
      await qc.invalidateQueries({ predicate: (k) => String(k.queryKey[0]).startsWith("/manage/") });
      onClose();
    } catch (e) { toastError(e); }
  };
  return (
    <Modal opened onClose={onClose} title={protest ? "Edit protest" : "File a protest"} size="lg">
      <Stack>
        <Select label="Protestor" clearable placeholder="Race committee" data={options} value={protestor} onChange={setProtestor} searchable />
        <MultiSelect label="Protested boat(s)" data={options} value={protestees} onChange={setProtestees} searchable />
        <TextInput label="Rule(s) alleged broken" list="rule-suggestions" value={rules} onChange={(e) => setRules(e.currentTarget.value)} />
        <datalist id="rule-suggestions">{RULE_SUGGESTIONS.map((r) => <option key={r} value={r} />)}</datalist>
        <Group grow>
          <TextInput label="Date filed" type="date" value={filedOn} onChange={(e) => setFiledOn(e.currentTarget.value)} />
          <Select label="Status" allowDeselect={false} value={status} onChange={(v) => setStatus(v ?? "filed")}
            data={[{ value: "filed", label: "Filed" }, { value: "heard", label: "Heard" }, { value: "decided", label: "Decided" }, { value: "withdrawn", label: "Withdrawn" }]} />
        </Group>
        <Textarea label="Decision (editors only)" minRows={3} value={decision} onChange={(e) => setDecision(e.currentTarget.value)}
          description="After deciding, record any penalty or redress on the boat's finish with a reason; that reason is what the public sees." />
        <Group justify="space-between">
          {protest ? <Button color="red" variant="subtle" onClick={remove}>Delete</Button> : <span />}
          <Button onClick={save}>Save</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
