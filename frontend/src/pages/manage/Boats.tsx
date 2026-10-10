import {
  Alert, Button, Card, FileInput, Group, Stack, Table, Text, TextInput, Title,
} from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, useGet, type S } from "../../api/client";
import { BoatForm, RatingsModal } from "../../components/BoatEditors";
import { Query, toastError, toastOk } from "../../components/bits";

type Boat = S["BoatOut"];

export default function Boats() {
  const boats = useGet<Boat[]>("/manage/boats");
  const typesRaw = useGet<S["RatingTypeIO"][]>("/manage/rating-types");
  // Time-on-time types (ORCA) always go in the far-right column, after the PHRF types.
  const types = {
    ...typesRaw,
    data: typesRaw.data && [...typesRaw.data].sort(
      (a, b) => Number(a.method === "tot") - Number(b.method === "tot") || (a.display_order ?? 0) - (b.display_order ?? 0)),
  };
  const fleets = useGet<S["FleetIO"][]>("/manage/fleets");
  const [editing, setEditing] = useState<Boat | "new" | null>(null);
  const [ratingsFor, setRatingsFor] = useState<number | null>(null);
  const today = new Date().toISOString().slice(0, 10);

  const current = (b: Boat, typeId: number | null | undefined) =>
    b.ratings.filter((r) => r.rating_type_id === typeId && r.effective_from <= today)
      .sort((a, c) => (a.effective_from < c.effective_from ? 1 : -1))[0];

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Boats &amp; ratings</Title>
        <Button onClick={() => setEditing("new")}>Add boat</Button>
      </Group>
      <Query q={boats}>
        {(list) => (
          <Table.ScrollContainer minWidth={700}>
            <Table striped withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Boat</Table.Th><Table.Th>Sail #</Table.Th><Table.Th>Design</Table.Th><Table.Th>Fleet</Table.Th><Table.Th>Member</Table.Th>
                  {types.data?.map((t) => <Table.Th key={t.id} ta="right">{t.code}</Table.Th>)}
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {list.map((b) => (
                  <Table.Tr key={b.id}>
                    <Table.Td>{b.name}</Table.Td><Table.Td>{b.sail_number}</Table.Td><Table.Td>{b.design}</Table.Td>
                    <Table.Td>{fleets.data?.find((f) => f.id === (b.default_fleet_id ?? -1))?.name ?? ""}</Table.Td>
                    <Table.Td>{b.is_member ? "\u2713" : ""}</Table.Td>
                    {types.data?.map((t) => {
                      const r = current(b, t.id);
                      return <Table.Td key={t.id} ta="right" c={r?.expires && r.expires < today ? "red" : undefined}>{r ? r.value : "—"}</Table.Td>;
                    })}
                    <Table.Td>
                      <Group gap={4} wrap="nowrap">
                        <Button size="compact-xs" variant="default" onClick={() => setEditing(b)}>Edit</Button>
                        <Button size="compact-xs" variant="default" onClick={() => setRatingsFor(b.id)}>Ratings</Button>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Query>
      <ImportCard />
      {editing && fleets.data && (
        <BoatForm boat={editing === "new" ? null : editing} fleets={fleets.data} types={types.data ?? []} onClose={() => setEditing(null)} />
      )}
      {ratingsFor !== null && boats.data && types.data && (
        <RatingsModal boat={boats.data.find((b) => b.id === ratingsFor)!} types={types.data} onClose={() => setRatingsFor(null)} />
      )}
    </Stack>
  );
}

function ImportCard() {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [eff, setEff] = useState(new Date().toISOString().slice(0, 10));
  const [res, setRes] = useState<S["ImportOut"] | null>(null);
  const run = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("effective_from", eff);
    form.append("file", file);
    try {
      setRes(await api<S["ImportOut"]>("/manage/boats/import", { method: "POST", form }));
      toastOk("Import finished");
      await qc.invalidateQueries({ queryKey: ["/manage/boats"] });
    } catch (e) { toastError(e); }
  };
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Title order={4}>Import boats from CSV</Title>
        <Text size="sm" c="dimmed">Columns: sail, name, design, skipper, fleet, plus one column per rating type code (e.g. WL, RL).</Text>
        <Group align="flex-end">
          <FileInput label="CSV file" accept=".csv,text/csv" value={file} onChange={setFile} />
          <TextInput label="Ratings effective from" type="date" value={eff} onChange={(e) => setEff(e.currentTarget.value)} />
          <Button onClick={run} disabled={!file}>Import</Button>
        </Group>
        {res && (
          <Alert color={res.errors.length ? "yellow" : "green"}>
            {res.boats_created} created, {res.boats_updated} updated, {res.ratings_saved} ratings saved.
            {res.errors.map((e) => <div key={e}>{e}</div>)}
          </Alert>
        )}
      </Stack>
    </Card>
  );
}
