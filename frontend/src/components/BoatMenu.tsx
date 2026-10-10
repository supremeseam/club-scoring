import { ActionIcon, Alert, Button, Checkbox, Group, Menu, Modal, Radio, Select, Stack, Text } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, useGet, type S } from "../api/client";
import { BoatForm, RatingsModal } from "./BoatEditors";
import { toastError, toastOk } from "./bits";

type Props = {
  boat: S["BoatOut"];
  startId: number;
  startFleetId: number;
  fleets: S["FleetIO"][];           // the fleets this series uses
  hasResult: boolean;
  defaultTypeId?: number | null;    // the rating type this start uses
  raceDate?: string;                // ratings added from a race take effect from the race date
};

const refresh = (qc: ReturnType<typeof useQueryClient>) =>
  qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/manage/") });

/** The "..." menu on a boat in the RC screen: change its fleet, clear its result, or remove it. */
export function BoatMenu(p: Props) {
  const [dialog, setDialog] = useState<"move" | "remove" | "edit" | "ratings" | null>(null);
  const allFleets = useGet<S["FleetIO"][]>("/manage/fleets");
  const types = useGet<S["RatingTypeIO"][]>("/manage/rating-types");
  return (
    <>
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <ActionIcon variant="subtle" color="gray" aria-label={`Actions for ${p.boat.name}`}>{"⋯"}</ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item onClick={() => setDialog("edit")}>Edit boat details{"\u2026"}</Menu.Item>
          <Menu.Item onClick={() => setDialog("ratings")}>Ratings{"\u2026"}</Menu.Item>
          <Menu.Divider />
          <Menu.Item onClick={() => setDialog("move")} disabled={p.fleets.length < 2}>Change fleet{"…"}</Menu.Item>
          <Menu.Item onClick={() => setDialog("remove")} color="red">Remove from race{"…"}</Menu.Item>
        </Menu.Dropdown>
      </Menu>
      {dialog === "edit" && allFleets.data && types.data && (
        <BoatForm boat={p.boat} fleets={allFleets.data} types={types.data} onClose={() => setDialog(null)} />
      )}
      {dialog === "ratings" && types.data && (
        <RatingsModal boat={p.boat} types={types.data} onClose={() => setDialog(null)} defaultTypeId={p.defaultTypeId}
          defaultEffective={p.raceDate} />
      )}
      {dialog === "move" && <MoveDialog {...p} onClose={() => setDialog(null)} />}
      {dialog === "remove" && <RemoveDialog {...p} onClose={() => setDialog(null)} />}
    </>
  );
}

function MoveDialog({ boat, startId, startFleetId, fleets, hasResult, onClose }: Props & { onClose: () => void }) {
  const qc = useQueryClient();
  const options = fleets.filter((f) => f.id !== startFleetId).map((f) => ({ value: String(f.id), label: f.name }));
  const [to, setTo] = useState<string | null>(options[0]?.value ?? null);
  const [scope, setScope] = useState<"race" | "series">(hasResult ? "race" : "series");
  const [moveThisRace, setMoveThisRace] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const go = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await api<S["MoveBoatOut"]>(`/manage/starts/${startId}/move-boat`, {
        method: "POST",
        body: { boat_id: boat.id, to_fleet_id: Number(to), scope, move_this_race: moveThisRace },
      });
      toastOk(r.moved_result ? `${boat.name} moved` : `${boat.name}'s fleet changed`);
      r.warnings.forEach((w) => toastError(new Error(w)));
      await refresh(qc);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };

  return (
    <Modal opened onClose={onClose} title={`Change fleet: ${boat.name}`}>
      <Stack>
        <Select label="Move to" data={options} value={to} onChange={setTo} allowDeselect={false} />
        <Radio.Group value={scope} onChange={(v) => setScope(v as "race" | "series")}>
          <Stack gap={6}>
            <Radio value="race" disabled={!hasResult} label="This race only"
              description={hasResult ? "Its result in this race moves to that fleet's start and is rescored. Its series fleet is unchanged."
                : "Enter a finish time or status for this boat first."} />
            <Radio value="series" label="The rest of the series"
              description="Its fleet changes in the standings. Results in earlier races stay where it raced." />
          </Stack>
        </Radio.Group>
        {scope === "series" && hasResult && (
          <Checkbox label="Also move this race's result" checked={moveThisRace} onChange={(e) => setMoveThisRace(e.currentTarget.checked)} />
        )}
        {error && <Alert color="orange">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button onClick={go} loading={busy} disabled={!to}>Change fleet</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function RemoveDialog({ boat, startId, hasResult, onClose }: Props & { onClose: () => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async (removeEntry: boolean) => {
    setBusy(true);
    setError("");
    try {
      await api<S["RemoveBoatOut"]>(`/manage/starts/${startId}/boats/${boat.id}?remove_entry=${removeEntry}`, { method: "DELETE" });
      toastOk(removeEntry ? `${boat.name} removed from the series` : `${boat.name}'s result cleared`);
      await refresh(qc);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };
  return (
    <Modal opened onClose={onClose} title={`Remove ${boat.name}`}>
      <Stack>
        <Text size="sm"><b>Clear this race's result</b>: deletes the finish time, status and penalty{hasResult ? "" : " (none entered yet)"}. {boat.name} stays
          entered in the series and scores DNC for this race unless it has a result.</Text>
        <Text size="sm"><b>Remove from the series</b>: also takes {boat.name} out of the entry list. Only possible when it has no results in other races.
          Payments already recorded are kept.</Text>
        {error && <Alert color="orange">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button variant="light" color="red" loading={busy} onClick={() => go(false)}>Clear this race's result</Button>
          <Button color="red" loading={busy} onClick={() => go(true)}>Remove from series</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
