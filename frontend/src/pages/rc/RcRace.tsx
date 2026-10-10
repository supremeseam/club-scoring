import {
  Alert, Badge, Button, Card, Checkbox, Group, NumberInput, Select, SimpleGrid, Stack, Text, TextInput, Title,
} from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, useGet, type S } from "../../api/client";
import { Query, toastError, toastOk } from "../../components/bits";
import { BoatMenu } from "../../components/BoatMenu";
import { RatingsModal } from "../../components/BoatEditors";
import { defaultFee } from "../../components/Payments";
import { Protests } from "../../components/Protests";
import { RULE_SUGGESTIONS, STATUS_CODES, STATUS_INFO } from "../../lib/penalties";
import { ResultsTable } from "../../components/tables";
import { addDays, dateOf, nowHms, parseTimeInput, timeOf } from "../../lib/time";

const refreshManage = (qc: ReturnType<typeof useQueryClient>) =>
  qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/manage/") });

export default function RcRace() {
  const { raceId } = useParams();
  const qc = useQueryClient();
  const race = useGet<S["RaceEditor"]>(`/manage/races/${raceId}`);
  const refresh = () => qc.invalidateQueries({ queryKey: [`/manage/races/${raceId}`] });
  return <Query q={race}>{(r) => <RaceBody race={r} onRaceChanged={refresh} />}</Query>;
}

function RaceBody({ race, onRaceChanged }: { race: S["RaceEditor"]; onRaceChanged: () => void }) {
  const series = useGet<S["SeriesEditor"][]>("/manage/series");
  const fleets = useGet<S["FleetIO"][]>("/manage/fleets");
  const courses = useGet<S["CourseOut"][]>("/manage/courses");
  const types = useGet<S["RatingTypeIO"][]>("/manage/rating-types");
  const entries = useGet<S["EntryIO"][]>(`/manage/series/${race.series_id}/entries`);
  const boats = useGet<S["BoatOut"][]>("/manage/boats");
  const starts = useGet<S["StartOut"][]>(`/manage/races/${race.id}/starts`);
  const lineup = useGet<S["LineupRow"][]>(`/manage/races/${race.id}/lineup`);
  const payments = useGet<S["PaymentOut"][]>(`/manage/series/${race.series_id}/payments`);
  const ser = series.data?.find((x) => x.id === race.series_id);

  const setStatus = async (status: string | null, final?: boolean, membersFree?: boolean) => {
    try {
      await api(`/manage/races/${race.id}`, {
        method: "PUT",
        body: { date: race.date, status: status ?? race.status, time_limit_minutes: race.time_limit_minutes,
                results_final: final ?? race.results_final, number: race.number,
                members_free: membersFree ?? race.members_free },
      });
      onRaceChanged();
    } catch (e) { toastError(e); }
  };

  const ready = fleets.data && courses.data && types.data && entries.data && boats.data && starts.data && lineup.data && ser;
  const single = ser?.kind === "single";
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>
          {ser ? (single ? ser.name : `${ser.name} ${ser.season}`) : ""} {!single && <>{"·"} Race {race.number}</>}
        </Title>
        <Badge color={race.results_final ? "green" : "yellow"}>{race.results_final ? "Final" : "Provisional"}</Badge>
      </Group>
      <Group align="flex-end">
        <Select label="Race status" w={160} value={race.status} allowDeselect={false}
          data={["scheduled", "sailed", "abandoned", "cancelled"]} onChange={(v) => setStatus(v)} />
        <Checkbox label="Results final" checked={race.results_final} onChange={(e) => setStatus(null, e.currentTarget.checked)} />
        {ser?.require_payment && (
          <Checkbox label="Members race free" checked={race.members_free}
            onChange={(e) => setStatus(null, undefined, e.currentTarget.checked)} />
        )}
        <Text size="sm" c="dimmed">{race.date}{single ? " · single race (not part of a series)" : ""}</Text>
      </Group>
      {race.status === "scheduled" && (
        <Alert color="blue">Set the race status to <b>sailed</b> once the first start goes, so results are scored and published.</Alert>
      )}
      {!ready ? null : [...ser.fleet_ids]
        .sort((a, b) => (fleets.data!.findIndex((f) => f.id === a)) - (fleets.data!.findIndex((f) => f.id === b)))
        .map((fid) => {
        const fleet = fleets.data!.find((f) => f.id === fid);
        if (!fleet) return null;
        // a boat sits in the start it raced in (see /lineup), so a moved boat shows on the right panel
        const boatIds = lineup.data!.find((l) => l.fleet_id === fid)?.boat_ids ?? [];
        return (
          <FleetPanel key={fid} race={race} fleet={fleet} courses={courses.data!} types={types.data!}
            start={starts.data!.find((s) => s.fleet_id === fid)} single={single}
            allBoats={boats.data!} entered={entries.data!.map((e) => e.boat_id)}
            series={ser} payments={payments.data ?? []}
            seriesFleets={ser.fleet_ids.map((id) => fleets.data!.find((f) => f.id === id)).filter((f): f is S["FleetIO"] => !!f)}
            boats={boats.data!.filter((b) => boatIds.includes(b.id))} />
        );
      })}
      {boats.data && <Protests raceId={race.id} boats={boats.data} />}
      <Results raceId={race.id} />
    </Stack>
  );
}

function Results({ raceId }: { raceId: number }) {
  const q = useGet<S["RaceResults"]>(`/manage/races/${raceId}/results`);
  return (
    <Stack>
      <Title order={3}>Results preview</Title>
      <Query q={q}>{(r) => <>{r.fleets.map((b) => (
        <Stack key={b.fleet_id} gap={4}><Text fw={600}>{b.fleet_name}</Text><ResultsTable block={b} /></Stack>
      ))}</>}</Query>
    </Stack>
  );
}

type Row = { time: string; date: string; status: string; penalty: number; redress: number | ""; manual: number | ""; note: string };
const blank: Row = { time: "", date: "", status: "", penalty: 0, redress: "", manual: "", note: "" };

function FleetPanel({ race, fleet, courses, types, start, boats, allBoats, entered, single, series, payments, seriesFleets }: {
  race: S["RaceEditor"]; fleet: S["FleetIO"]; courses: S["CourseOut"][]; types: S["RatingTypeIO"][];
  start: S["StartOut"] | undefined; boats: S["BoatOut"][]; allBoats: S["BoatOut"][]; entered: number[]; single: boolean;
  series: S["SeriesEditor"]; payments: S["PaymentOut"][]; seriesFleets: S["FleetIO"][];
}) {
  const qc = useQueryClient();
  const [course, setCourse] = useState<string | null>(start?.course_id ? String(start.course_id) : null);
  const [rtype, setRtype] = useState<string | null>(start ? String(start.rating_type_id) : null);
  const [startDate, setStartDate] = useState(start ? dateOf(start.start_time) : race.date);
  const [startTime, setStartTime] = useState(start ? timeOf(start.start_time) : "18:00:00");
  const [dist, setDist] = useState<number | "">(start?.distance_override ?? "");
  const [busy, setBusy] = useState(false);

  const pickCourse = (v: string | null) => {
    setCourse(v);
    const c = courses.find((x) => String(x.id) === v);
    if (c) setRtype(String(c.course_type_id)); // the course's type fills in; the RC can still override it
  };
  const courseObj = courses.find((c) => String(c.id) === course);
  // What the calculation needs: a rating type, a date and time, and (time-on-distance) a distance.
  const rt = types.find((x) => String(x.id) === rtype);
  const needsDistance = rt?.method === "tod";
  const distance = dist !== "" ? dist : Number(courseObj?.distance_nm ?? 0);
  const timeOk = !!parseTimeInput(startTime);
  const distanceOk = !needsDistance || distance > 0;
  const startOk = !!rtype && !!startDate && timeOk && distanceOk;

  const saveStart = async () => {
    const t = parseTimeInput(startTime);
    if (!t) return toastError(new Error("Start time is not valid"));
    if (!startDate) return toastError(new Error("Pick a start date"));
    setBusy(true);
    try {
      const r = await api<S["StartOut"]>(`/manage/races/${race.id}/starts`, {
        method: "PUT",
        body: { fleet_id: fleet.id, course_id: course ? Number(course) : null, start_time: `${startDate}T${t}`,
                distance_override: dist === "" ? null : dist, rating_type_id: rtype ? Number(rtype) : null },
      });
      toastOk(r.rating_changes ? `Start saved; ${r.rating_changes} ratings re-resolved` : "Start saved");
      await refreshManage(qc);
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };

  return (
    <Card withBorder padding="sm">
      <Stack gap="sm">
        <Title order={4}>{fleet.name}</Title>
        <SimpleGrid cols={{ base: 1, sm: 3, md: 5 }}>
          <Select label="Course" clearable data={courses.map((c) => ({ value: String(c.id), label: `${c.name} (${Number(c.distance_nm).toFixed(2)} nm)` }))}
            value={course} onChange={pickCourse} />
          <Select label="Rating type" withAsterisk allowDeselect={false} data={types.map((t) => ({ value: String(t.id), label: t.code }))}
            value={rtype} onChange={setRtype} error={!rtype ? "Required" : undefined} />
          <TextInput label="Start date" withAsterisk type="date" value={startDate} onChange={(e) => setStartDate(e.currentTarget.value)}
            description={startDate !== race.date ? "differs from race date" : undefined} />
          <TextInput label="Start time" withAsterisk error={!timeOk ? "Enter a time, e.g. 11:30:00" : undefined} value={startTime} onChange={(e) => setStartTime(e.currentTarget.value)}
            onBlur={() => setStartTime(parseTimeInput(startTime) ?? startTime)} inputMode="numeric" />
          <NumberInput label={needsDistance ? "Distance (nm)" : "Distance (nm, not used for TCF)"} withAsterisk={needsDistance}
            error={needsDistance && !distanceOk ? "Required: pick a course with a distance, or enter it" : undefined}
            placeholder={courseObj ? String(courseObj.distance_nm) : ""}
            value={dist} onChange={(v) => setDist(v === "" ? "" : Number(v))} min={0} decimalScale={2} />
        </SimpleGrid>
        <Group>
          <Button onClick={saveStart} loading={busy} disabled={!startOk}>{start ? "Update start" : "Set start"}</Button>
        </Group>
        <AddBoat fleet={fleet} raceSeriesId={race.series_id} allBoats={allBoats} entered={entered} single={single} />
        {start && <RatingPreview startId={start.id} rtypeId={start.rating_type_id} types={types} allBoats={allBoats} raceDate={race.date} />}
        {start && <Finishes start={start} boats={boats} fleetName={fleet.name} race={race} series={series} payments={payments} seriesFleets={seriesFleets} />}
      </Stack>
    </Card>
  );
}

function AddBoat({ fleet, raceSeriesId, allBoats, entered, single }: {
  fleet: S["FleetIO"]; raceSeriesId: number; allBoats: S["BoatOut"][]; entered: number[]; single: boolean;
}) {
  const qc = useQueryClient();
  const [pick, setPick] = useState<string | null>(null);
  const [guest, setGuest] = useState(true);
  const options = allBoats.filter((b) => !entered.includes(b.id)).map((b) => ({ value: String(b.id), label: `${b.name} (${b.sail_number})` }));
  const add = async () => {
    try {
      await api(`/manage/series/${raceSeriesId}/entries/add`, {
        method: "POST", body: { boat_id: Number(pick), fleet_id: fleet.id, in_series: single ? true : !guest },
      });
      setPick(null);
      await refreshManage(qc);
    } catch (e) { toastError(e); }
  };
  return (
    <Group align="flex-end" gap="xs">
      <Select label={single ? "Add a boat to this race" : "Add a boat for this race"} searchable clearable placeholder="Search boats"
        data={options} value={pick} onChange={setPick} w={260} />
      {!single && <Checkbox label="Guest (not scored in the series)" checked={guest} onChange={(e) => setGuest(e.currentTarget.checked)} />}
      <Button variant="default" onClick={add} disabled={!pick}>Add</Button>
    </Group>
  );
}

function RatingPreview({ startId, rtypeId, types, allBoats, raceDate }: {
  startId: number; rtypeId: number; types: S["RatingTypeIO"][]; allBoats: S["BoatOut"][]; raceDate: string;
}) {
  const q = useGet<S["RatingPreviewRow"][]>(`/manage/starts/${startId}/rating-preview`);
  const [adding, setAdding] = useState<number | null>(null);
  if (!q.data) return null;
  const addFor = allBoats.find((b) => b.id === adding);
  const missing = q.data.filter((r) => r.missing);
  const expired = q.data.filter((r) => r.expired);
  const fb = q.data.filter((r) => r.source === "fallback");
  return (
    <Stack gap={4}>
      {missing.length > 0 && (
        <Alert color="red" title="Missing ratings">
          <Stack gap={6}>
            <span>These boats have no rating of this type. Add it here, or enter one manually when scoring.</span>
            <Group gap={6}>
              {missing.map((m) => (
                <Button key={m.boat_id} size="compact-xs" color="red" variant="light" onClick={() => setAdding(m.boat_id)}>
                  Add {types.find((x) => x.id === rtypeId)?.code} rating for {m.boat}
                </Button>
              ))}
            </Group>
          </Stack>
        </Alert>
      )}
      {expired.length > 0 && <Alert color="orange">Certificate expired: {expired.map((m) => m.boat).join(", ")}</Alert>}
      {fb.length > 0 && <Alert color="yellow">Using fallback rating: {fb.map((m) => `${m.boat} (${m.rating})`).join(", ")}</Alert>}
      {addFor && (
        <RatingsModal boat={addFor} types={types} defaultTypeId={addFor.fixed_rating_type_id ?? rtypeId}
          defaultEffective={raceDate} onClose={() => setAdding(null)} />
      )}
    </Stack>
  );
}

function Finishes({ start, boats, fleetName, race, series, payments, seriesFleets }: {
  start: S["StartOut"]; boats: S["BoatOut"][]; fleetName: string; race: S["RaceEditor"];
  series: S["SeriesEditor"]; payments: S["PaymentOut"][]; seriesFleets: S["FleetIO"][];
}) {
  const qc = useQueryClient();
  const existing = useGet<S["FinishOut"][]>(`/manage/starts/${start.id}/finishes`);
  const preview = useGet<S["RatingPreviewRow"][]>(`/manage/starts/${start.id}/rating-preview`);
  const [rows, setRows] = useState<Record<number, Row>>({});
  const [busy, setBusy] = useState(false);
  const startIso = start.start_time;
  const startDate = dateOf(startIso);

  useEffect(() => {
    if (!existing.data) return;
    const next: Record<number, Row> = {};
    for (const f of existing.data) {
      next[f.boat_id] = {
        time: f.finish_time ? timeOf(f.finish_time) : "", date: f.finish_time ? dateOf(f.finish_time) : "",
        status: f.status, penalty: Number(f.penalty_pct), redress: f.redress_points ?? "", manual: "", note: f.note ?? "",
      };
    }
    setRows(next);
  }, [existing.data]);

  const get = (id: number) => rows[id] ?? blank;
  const patch = (id: number, p: Partial<Row>) => setRows((r) => ({ ...r, [id]: { ...(r[id] ?? blank), ...p } }));
  const missingRating = useMemo(() => new Set((preview.data ?? []).filter((p) => p.missing).map((p) => p.boat_id)), [preview.data]);
  const finishDate = (r: Row) => r.date || startDate;      // defaults to the day the race started

  const payStatus = (b: S["BoatOut"]): "series" | "race" | "member" | "unpaid" => {
    if (payments.some((p) => p.boat_id === b.id && p.race_id === null)) return "series";
    if (payments.some((p) => p.boat_id === b.id && p.race_id === race.id)) return "race";
    if (b.is_member && race.members_free) return "member";
    return "unpaid";
  };
  const recordPayment = async (b: S["BoatOut"]) => {
    try {
      await api(`/manage/series/${series.id}/payments`, { method: "POST", body: { boat_id: b.id, race_id: race.id } });
      toastOk(`Payment recorded for ${b.name}`);
      await refreshManage(qc);
    } catch (e) { toastError(e); }
  };

  const problems = boats.flatMap((b) => {
    const r = get(b.id);
    const t = parseTimeInput(r.time);
    const out: string[] = [];
    if (r.time && !t) out.push(`${b.name}: bad time`);
    if (t && `${finishDate(r)}T${t}` < startIso) out.push(`${b.name}: finish is before the start; change the finish date`);
    const hasRating = (existing.data ?? []).some((f) => f.boat_id === b.id && f.rating_value !== null);
    if (r.status === "SCP" && !(r.penalty > 0)) out.push(`${b.name}: enter the scoring penalty %`);
    if (t && missingRating.has(b.id) && !hasRating && r.manual === "" && !r.status) out.push(`${b.name}: needs a manual rating`);
    return out;
  });

  const save = async () => {
    setBusy(true);
    try {
      const items = boats.flatMap((b) => {
        const r = get(b.id);
        const t = parseTimeInput(r.time);
        if (!t && !r.status) return [];
        return [{
          boat_id: b.id, status: r.status, finish_time: t ? `${finishDate(r)}T${t}` : null,
          penalty_pct: r.penalty, redress_points: r.redress === "" ? null : r.redress,
          manual_rating: r.manual === "" ? null : r.manual, note: r.note,
        }];
      });
      for (const f of existing.data ?? []) {
        const r = get(f.boat_id);
        if (!r.time && !r.status) await api(`/manage/finishes/${f.id}`, { method: "DELETE" });
      }
      await api(`/manage/starts/${start.id}/finishes`, { method: "PUT", body: items });
      toastOk("Finishes saved");
      await refreshManage(qc);
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };

  return (
    <Stack gap="xs">
      <Text fw={600}>{fleetName} finishes</Text>
      {boats.map((b) => {
        const r = get(b.id);
        const t = parseTimeInput(r.time);
        const before = t && `${finishDate(r)}T${t}` < startIso;
        return (
          <Card key={b.id} withBorder padding="xs">
            <Group wrap="wrap" align="flex-end" gap="xs">
              <div style={{ minWidth: 130, flex: "1 1 130px" }}>
                <Text fw={600} size="sm">{b.name} {b.is_member && <Badge size="xs" variant="light">member</Badge>}</Text>
                <Text size="xs" c="dimmed">{b.sail_number}</Text>
                {series.require_payment && (() => {
                  const s = payStatus(b);
                  return s === "unpaid" ? (
                    <Group gap={4} mt={2}>
                      <Badge size="xs" color="red">unpaid: scored as guest</Badge>
                      <Button size="compact-xs" variant="light" onClick={() => recordPayment(b)}>
                        Paid ${defaultFee(series, b.is_member, true)}
                      </Button>
                    </Group>
                  ) : <Badge size="xs" color="teal" variant="light" mt={2}>{s === "member" ? "member: free race" : `paid (${s})`}</Badge>;
                })()}
              </div>
              <BoatMenu boat={b} startId={start.id} startFleetId={start.fleet_id} fleets={seriesFleets}
                defaultTypeId={b.fixed_rating_type_id ?? start.rating_type_id} raceDate={race.date}
                hasResult={(existing.data ?? []).some((f) => f.boat_id === b.id)} />
              <TextInput aria-label={`Finish date ${b.name}`} type="date" w={150} value={finishDate(r)}
                onChange={(e) => patch(b.id, { date: e.currentTarget.value })} />
              <TextInput aria-label={`Finish time ${b.name}`} placeholder="hh:mm:ss" w={110} inputMode="numeric" value={r.time}
                error={r.time && !t ? "bad time" : undefined}
                onChange={(e) => patch(b.id, { time: e.currentTarget.value })}
                onBlur={() => patch(b.id, { time: parseTimeInput(r.time) ?? r.time })} />
              <Button size="sm" variant="light" aria-label={`Stamp now ${b.name}`}
                onClick={() => patch(b.id, { time: nowHms(), status: "" })}>Now</Button>
              <Select aria-label={`Status ${b.name}`} placeholder="status" w={105} clearable
                data={STATUS_CODES.map((c) => ({ value: c, label: c }))} value={r.status || null}
                renderOption={({ option }) => <div><b>{option.value}</b> <Text span size="xs" c="dimmed">{STATUS_INFO[option.value]?.label}</Text></div>}
                comboboxProps={{ width: 330, position: "bottom-start" }}
                onChange={(v) => {
                  const info = v ? STATUS_INFO[v] : undefined;
                  patch(b.id, {
                    status: v ?? "",
                    note: r.note || info?.note || "",                         // pre-fill the standard reason
                    penalty: v === "SCP" && !r.penalty ? info?.pct ?? 0 : r.penalty,
                  });
                }} />
              {r.status === "SCP" && (
                <NumberInput aria-label="Penalty percent" w={80} suffix="%" value={r.penalty} min={0} max={100}
                  onChange={(v) => patch(b.id, { penalty: Number(v) || 0 })} />
              )}
              {r.status === "RDG" && (
                <NumberInput aria-label="Redress points" placeholder="pts (blank = avg)" w={120} value={r.redress} min={0}
                  onChange={(v) => patch(b.id, { redress: v === "" ? "" : Number(v) })} />
              )}
              {missingRating.has(b.id) && (
                <NumberInput aria-label={`Manual rating ${b.name}`} placeholder="rating" w={90} value={r.manual}
                  onChange={(v) => patch(b.id, { manual: v === "" ? "" : Number(v) })} />
              )}
            </Group>
            {(r.status || r.note) && (
              <TextInput mt={6} size="xs" list="penalty-rules" placeholder="Reason for the penalty or score (shown publicly)"
                aria-label={`Reason ${b.name}`} value={r.note} maxLength={300}
                error={r.status && STATUS_INFO[r.status]?.needsReason && !r.note ? "Add a reason; it is shown on the results" : undefined}
                onChange={(e) => patch(b.id, { note: e.currentTarget.value })} />
            )}
            {before && (
              <Button mt={6} size="compact-xs" color="orange" variant="light"
                onClick={() => patch(b.id, { date: addDays(finishDate(r), 1) })}>
                Finished after midnight? Use next day ({addDays(finishDate(r), 1)})
              </Button>
            )}
          </Card>
        );
      })}
      <datalist id="penalty-rules">{RULE_SUGGESTIONS.map((x) => <option key={x} value={x} />)}</datalist>
      {problems.length > 0 && <Alert color="orange">{problems.join(" · ")}</Alert>}
      <div style={{ position: "sticky", bottom: 8 }}>
        <Button fullWidth size="md" onClick={save} loading={busy} disabled={problems.length > 0}>
          Save {fleetName} finishes
        </Button>
      </div>
    </Stack>
  );
}
