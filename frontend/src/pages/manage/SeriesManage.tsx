import {
  Badge, Button, Card, Checkbox, Group, Modal, MultiSelect, NumberInput, Select, SimpleGrid, Stack, Table, Text,
  TextInput, Title,
} from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, useGet, type S } from "../../api/client";
import { PaymentsPanel } from "../../components/Payments";
import { Query, toastError, toastOk } from "../../components/bits";

type Series = S["SeriesEditor"];

export default function SeriesManage() {
  const list = useGet<Series[]>("/manage/series");
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Series</Title>
        <Button onClick={() => setCreating(true)}>New series</Button>
      </Group>
      <Query q={list}>
        {(rows) => (
          <Table highlightOnHover withTableBorder>
            <Table.Thead><Table.Tr><Table.Th>Series</Table.Th><Table.Th>Season</Table.Th><Table.Th>Status</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {rows.map((s) => (
                <Table.Tr key={s.id} onClick={() => setSelected(s.id)} style={{ cursor: "pointer" }} bg={selected === s.id ? "var(--mantine-color-blue-light)" : undefined}>
                  <Table.Td>{s.name}</Table.Td><Table.Td>{s.season}</Table.Td>
                  <Table.Td><Badge color={s.status === "active" ? "blue" : s.status === "draft" ? "gray" : "green"}>{s.status}</Badge></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Query>
      {selected !== null && list.data && <Detail key={selected} series={list.data.find((s) => s.id === selected)!} />}
      {creating && <SeriesForm onClose={() => setCreating(false)} onSaved={(s) => { setCreating(false); setSelected(s.id); }} />}
    </Stack>
  );
}

function Detail({ series }: { series: Series }) {
  const [editing, setEditing] = useState(false);
  const qc = useQueryClient();
  const [season, setSeason] = useState<number | "">(series.season + 1);
  const clone = async () => {
    try {
      await api(`/manage/series/${series.id}/clone`, { method: "POST", body: { season, shift_days: 364 } });
      toastOk(`Copied to ${season}`);
      await qc.invalidateQueries({ queryKey: ["/manage/series"] });
    } catch (e) { toastError(e); }
  };
  return (
    <Card withBorder>
      <Stack>
        <Group justify="space-between">
          <Title order={3}>{series.name} {series.season}</Title>
          <Button variant="default" onClick={() => setEditing(true)}>Edit settings</Button>
        </Group>
        <Text size="sm">
          {series.race_format === "pursuit" ? "Pursuit start � " : ""}Scoring: {series.scoring_system === "high" ? "high point" : "low point"}{" \u00b7 "}Discards: {series.discard_thresholds.length ? series.discard_thresholds.map((t) => `1 after ${t} races`).join(", ") : "none"}
          {" · "}RC duty credit: {series.rcd_method}{" · "}Combined overall: {series.combined_overall ? "on" : "off"}
        </Text>
        <Entries series={series} />
        <PaymentsPanel series={series} />
        <Group align="flex-end">
          <NumberInput label="Copy to next season" w={160} value={season} onChange={(v) => setSeason(v === "" ? "" : Number(v))} />
          <Button variant="default" onClick={clone} disabled={season === ""}>Copy series (no results)</Button>
        </Group>
      </Stack>
      {editing && <SeriesForm series={series} onClose={() => setEditing(false)} onSaved={() => setEditing(false)} />}
    </Card>
  );
}

function Entries({ series }: { series: Series }) {
  const boats = useGet<S["BoatOut"][]>("/manage/boats");
  const fleets = useGet<S["FleetIO"][]>("/manage/fleets");
  const entries = useGet<S["EntryIO"][]>(`/manage/series/${series.id}/entries`);
  const qc = useQueryClient();
  const [sel, setSel] = useState<Record<number, { fleet: number; inSeries: boolean }> | null>(null);
  const current = sel ?? Object.fromEntries((entries.data ?? []).map((e) => [e.boat_id, { fleet: e.fleet_id, inSeries: e.in_series ?? true }]));
  const fleetOpts = (fleets.data ?? []).filter((f) => series.fleet_ids.includes(f.id ?? -1)).map((f) => ({ value: String(f.id), label: f.name }));

  const save = async () => {
    try {
      await api(`/manage/series/${series.id}/entries`, {
        method: "PUT", body: Object.entries(current).map(([b, f]) => ({ boat_id: Number(b), fleet_id: f.fleet, in_series: f.inSeries })),
      });
      toastOk("Entry list saved");
      setSel(null);
      await qc.invalidateQueries({ queryKey: [`/manage/series/${series.id}/entries`] });
    } catch (e) { toastError(e); }
  };
  return (
    <Query q={boats}>
      {(bs) => (
        <Stack gap="xs">
          <Text fw={600}>Entry list ({Object.keys(current).length} boats)</Text>
          <Text size="xs" c="dimmed">Entries set the DNC points (entries + 1). Guests race and show in race results but are not scored in the series. A boat added mid-series scores DNC for earlier races.</Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
            {bs.map((b) => (
              <Group key={b.id} wrap="nowrap" gap="xs">
                <Checkbox aria-label={`Enter ${b.name}`} checked={b.id in current}
                  onChange={(e) => {
                    const next = { ...current };
                    if (e.currentTarget.checked) next[b.id] = { fleet: b.default_fleet_id && series.fleet_ids.includes(b.default_fleet_id) ? b.default_fleet_id : series.fleet_ids[0], inSeries: true };
                    else delete next[b.id];
                    setSel(next);
                  }} />
                <Text size="sm" style={{ flex: 1 }}>{b.name} <Text span c="dimmed" size="xs">{b.sail_number}</Text></Text>
                {b.id in current && (
                  <>
                    <Select w={130} size="xs" allowDeselect={false} data={fleetOpts} value={String(current[b.id].fleet)}
                      onChange={(v) => v && setSel({ ...current, [b.id]: { ...current[b.id], fleet: Number(v) } })} />
                    <Checkbox size="xs" label="Guest" title="Races and appears in race results, but is not scored in the series"
                      checked={!current[b.id].inSeries}
                      onChange={(e) => setSel({ ...current, [b.id]: { ...current[b.id], inSeries: !e.currentTarget.checked } })} />
                  </>
                )}
              </Group>
            ))}
          </SimpleGrid>
          <Button w={180} onClick={save} disabled={sel === null}>Save entry list</Button>
        </Stack>
      )}
    </Query>
  );
}

function SeriesForm({ series, onClose, onSaved }: { series?: Series; onClose: () => void; onSaved: (s: Series) => void }) {
  const fleets = useGet<S["FleetIO"][]>("/manage/fleets");
  const qc = useQueryClient();
  const year = new Date().getFullYear();
  const [f, setF] = useState<S["SeriesIn"]>(series ?? {
    name: "", season: year, description: "", fleet_ids: [], discard_thresholds: [], scoring_basis: "entries", scoring_system: "low", race_format: "fleet",
    rcd_method: "off", rcd_max_credits: 2, tle_as: "DNF", combined_overall: false, status: "draft",
    require_payment: false, series_fee: 0, race_fee: 0, member_series_fee: null, member_race_fee: null,
  });
  const [discardAfter, setDiscardAfter] = useState<number | "">(f.discard_thresholds[0] ?? "");
  const [sched, setSched] = useState(false);
  const [first, setFirst] = useState(`${year}-05-06`);
  const [last, setLast] = useState(`${year}-08-26`);
  const [interval, setInterval_] = useState<number | "">(7);

  // everything the scoring needs before the series can be saved
  const feeMissing = f.require_payment && !(Number(f.series_fee) > 0 || Number(f.race_fee) > 0);
  const formOk = !!f.name.trim() && (f.fleet_ids ?? []).length > 0 && !feeMissing && (!sched || (!!first && !!last && first <= last));
  const save = async () => {
    const body: Record<string, unknown> = { ...f, discard_thresholds: discardAfter === "" ? [] : [discardAfter] };
    if (!series && sched) body.schedule = { first_date: first, last_date: last, interval_days: interval || 7 };
    try {
      const r = await api<Series>(series ? `/manage/series/${series.id}` : "/manage/series", { method: series ? "PUT" : "POST", body });
      await qc.invalidateQueries({ queryKey: ["/manage/series"] });
      onSaved(r);
    } catch (e) { toastError(e); }
  };
  return (
    <Modal opened onClose={onClose} title={series ? "Series settings" : "New series"} size="lg">
      <Stack>
        <Group grow>
          <TextInput label="Name" withAsterisk value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })}
            error={!f.name.trim() ? "Required" : undefined} />
          <NumberInput label="Season" value={f.season} onChange={(v) => setF({ ...f, season: Number(v) })} />
        </Group>
        <TextInput label="Description (shown on public page)" value={f.description ?? ""} onChange={(e) => setF({ ...f, description: e.currentTarget.value })} />
        <MultiSelect label="Fleets" withAsterisk error={(f.fleet_ids ?? []).length === 0 ? "Pick at least one fleet" : undefined}
          value={(f.fleet_ids ?? []).map(String)} onChange={(v) => setF({ ...f, fleet_ids: v.map(Number) })}
          data={(fleets.data ?? []).map((x) => ({ value: String(x.id), label: x.name }))} />
        <Select label="Race format" allowDeselect={false} value={f.race_format ?? "fleet"}
          description={f.race_format === "pursuit"
            ? "Pursuit start: the slowest boat starts first and the others are delayed by their handicap, so the first boat across the line wins. The race screen shows each boat's start time. A single race can override this."
            : "Fleet start: boats start together and results use corrected time."}
          data={[{ value: "fleet", label: "Fleet start (corrected time)" }, { value: "pursuit", label: "Pursuit start (first across the line wins)" }]}
          onChange={(v) => setF({ ...f, race_format: v ?? "fleet" })} />
        <Select label="Scoring system" allowDeselect={false} value={f.scoring_system ?? "low"}
          description={f.scoring_system === "high"
            ? "High point: 1st place scores the most points (the number of boats), each place one less, non-finishers 0. Highest total wins."
            : "Low point: 1st place scores 1 point, 2nd 2 points... Lowest total wins (the sailing rules default)."}
          data={[{ value: "low", label: "Low point (1st = 1 point)" }, { value: "high", label: "High point (1st = most points)" }]}
          onChange={(v) => setF({ ...f, scoring_system: v ?? "low" })} />
        <Group grow align="flex-end">
          <NumberInput label="One discard after N races" placeholder="none" value={discardAfter} min={1}
            onChange={(v) => setDiscardAfter(v === "" ? "" : Number(v))} />
          <Select label={f.scoring_system === "high" ? "Points for 1st place based on" : "Scoring basis for DNS/DNF/..."} allowDeselect={false} value={f.scoring_basis}
            data={[{ value: "entries", label: "Series entries + 1" }, { value: "starters", label: "Boats that came to the start + 1" }]}
            onChange={(v) => setF({ ...f, scoring_basis: v ?? "entries" })} />
        </Group>
        <Group grow align="flex-end">
          <Select label="RC duty credit" allowDeselect={false} value={f.rcd_method}
            data={[{ value: "off", label: "Off (scores as DNC)" }, { value: "all_other", label: "Average of all other races" }, { value: "before", label: "Average of races before" }]}
            onChange={(v) => setF({ ...f, rcd_method: v ?? "off" })} />
          <NumberInput label="Max credits per boat" min={0} value={f.rcd_max_credits} onChange={(v) => setF({ ...f, rcd_max_credits: Number(v) })} />
        </Group>
        <Checkbox label="Combined overall standings (all fleets, same-course races only)" checked={f.combined_overall}
          onChange={(e) => setF({ ...f, combined_overall: e.currentTarget.checked })} />
        <Checkbox label="Require payment to be scored (a boat scores only in races it paid for, or if it paid for the whole series)"
          checked={f.require_payment} onChange={(e) => setF({ ...f, require_payment: e.currentTarget.checked })} />
        <Group grow align="flex-end">
          <NumberInput label="Series fee" prefix="$" decimalScale={2} min={0} value={f.series_fee ?? 0}
            onChange={(v) => setF({ ...f, series_fee: Number(v) || 0 })} />
          <NumberInput label="Fee per race" prefix="$" decimalScale={2} min={0} value={f.race_fee ?? 0}
            onChange={(v) => setF({ ...f, race_fee: Number(v) || 0 })} />
        </Group>
        <Group grow align="flex-end">
          <NumberInput label="Member series fee" description="blank = same as everyone" prefix="$" decimalScale={2} min={0}
            value={f.member_series_fee ?? ""} onChange={(v) => setF({ ...f, member_series_fee: v === "" ? null : Number(v) })} />
          <NumberInput label="Member fee per race" description="blank = same as everyone" prefix="$" decimalScale={2} min={0}
            value={f.member_race_fee ?? ""} onChange={(v) => setF({ ...f, member_race_fee: v === "" ? null : Number(v) })} />
        </Group>
        <Select label="Status" allowDeselect={false} value={f.status} data={["draft", "active", "complete"]}
          onChange={(v) => setF({ ...f, status: v ?? "draft" })} />
        {!series && (
          <>
            <Checkbox label="Create a race schedule" checked={sched} onChange={(e) => setSched(e.currentTarget.checked)} />
            {sched && (
              <Group grow>
                <TextInput label="First race" type="date" value={first} onChange={(e) => setFirst(e.currentTarget.value)} />
                <TextInput label="Last race" type="date" value={last} onChange={(e) => setLast(e.currentTarget.value)} />
                <NumberInput label="Every N days" min={1} value={interval} onChange={(v) => setInterval_(v === "" ? "" : Number(v))} />
              </Group>
            )}
          </>
        )}
        {feeMissing && <Text size="sm" c="orange">Set a series fee or a fee per race, or turn off \u201cRequire payment\u201d.</Text>}
        <Button onClick={save} disabled={!formOk}>Save</Button>
      </Stack>
    </Modal>
  );
}
