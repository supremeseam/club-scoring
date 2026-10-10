import { Anchor, Badge, Button, Card, Checkbox, Group, MultiSelect, NumberInput, Select, Stack, Text, TextInput, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, useGet, type S } from "../../api/client";
import { Query, toastError } from "../../components/bits";
import { fmtDate } from "../../lib/time";

export default function RcHome() {
  const series = useGet<S["SeriesEditor"][]>("/manage/series");
  const [sid, setSid] = useState<string | null>(null);
  return (
    <Stack>
      <Title order={2}>Race committee</Title>
      <Query q={series}>
        {(list) => (
          <>
            <Select
              label="Series"
              placeholder="Pick a series"
              data={list.filter((s) => s.status !== "complete").map((s) => ({ value: String(s.id), label: s.kind === "single" ? `${s.name} (single race)` : `${s.name} ${s.season}` }))}
              value={sid}
              onChange={setSid}
            />
            {sid && <Races seriesId={Number(sid)} />}
            <SingleRace />
          </>
        )}
      </Query>
    </Stack>
  );
}

function Races({ seriesId }: { seriesId: number }) {
  const q = useGet<S["RaceEditor"][]>(`/manage/series/${seriesId}/races`);
  const qc = useQueryClient();
  const nav = useNavigate();
  const addRace = async () => {
    try {
      const r = await api<S["RaceEditor"]>(`/manage/series/${seriesId}/races`, {
        method: "POST",
        body: { date: new Date().toISOString().slice(0, 10), status: "scheduled" },
      });
      await qc.invalidateQueries({ queryKey: [`/manage/series/${seriesId}/races`] });
      nav(`/rc/races/${r.id}`);
    } catch (e) {
      toastError(e);
    }
  };
  return (
    <Query q={q}>
      {(races) => (
        <Stack gap="xs">
          <Group justify="space-between">
            <Text fw={600}>Races</Text>
            <Button size="xs" onClick={addRace}>New race today</Button>
          </Group>
          {races.map((r) => (
            <Group key={r.id} justify="space-between" p="xs" style={{ border: "1px solid var(--mantine-color-default-border)", borderRadius: 6 }}>
              <Anchor component={Link} to={`/rc/races/${r.id}`}>Race {r.number} {"·"} {fmtDate(r.date)}</Anchor>
              <Badge color={r.status === "sailed" ? "blue" : r.status === "scheduled" ? "gray" : "red"}>{r.status}</Badge>
            </Group>
          ))}
        </Stack>
      )}
    </Query>
  );
}

function SingleRace() {
  const fleets = useGet<S["FleetIO"][]>("/manage/fleets");
  const qc = useQueryClient();
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [fl, setFl] = useState<string[]>([]);
  const [requirePay, setRequirePay] = useState(false);
  const [fee, setFee] = useState<number | "">(0);
  const create = async () => {
    try {
      const r = await api<S["RaceEditor"]>("/manage/single-races", {
        method: "POST", body: { name, date, fleet_ids: fl.map(Number), require_payment: requirePay, race_fee: fee === "" ? 0 : fee },
      });
      await qc.invalidateQueries({ queryKey: ["/manage/series"] });
      nav(`/rc/races/${r.id}`);
    } catch (e) { toastError(e); }
  };
  return (
    <Card withBorder mt="md">
      <Stack gap="xs">
        <Text fw={600}>New single race (not part of a series)</Text>
        <Group align="flex-end">
          <TextInput label="Race name" placeholder="e.g. Around the Island" value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <TextInput label="Date" type="date" value={date} onChange={(e) => setDate(e.currentTarget.value)} />
          <MultiSelect label="Fleets" value={fl} onChange={setFl} data={(fleets.data ?? []).map((f) => ({ value: String(f.id), label: f.name }))} />
          <Checkbox label="Require entry fee" checked={requirePay} onChange={(e) => setRequirePay(e.currentTarget.checked)} />
          {requirePay && <NumberInput label="Fee" prefix="$" w={100} decimalScale={2} min={0} value={fee} onChange={(v) => setFee(v === "" ? "" : Number(v))} />}
          <Button onClick={create} disabled={!name || !date || fl.length === 0}>Create race</Button>
        </Group>
      </Stack>
    </Card>
  );
}
