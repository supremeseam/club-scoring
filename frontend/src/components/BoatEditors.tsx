import { Button, Checkbox, Group, Modal, NumberInput, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../api/client";
import { toastError } from "./bits";

type Boat = S["BoatOut"];
const refreshManage = (qc: ReturnType<typeof useQueryClient>) =>
  qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/manage/") });

/** Add or edit a boat. Shared by the Boats page and the race screen. */
export function BoatForm({ boat, fleets, types, onClose }: {
  boat: Boat | null; fleets: S["FleetIO"][]; types: S["RatingTypeIO"][]; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [f, setF] = useState<S["BoatIn"]>(
    boat ?? { name: "", sail_number: "", design: "", skipper: "", home_club: "", is_member: false, default_fleet_id: null, fixed_rating_type_id: null, contact_email: "", contact_phone: "", active: true },
  );
  const set = (k: keyof S["BoatIn"]) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.currentTarget.value });
  const save = async () => {
    try {
      await api(boat ? `/manage/boats/${boat.id}` : "/manage/boats", { method: boat ? "PUT" : "POST", body: f });
      await refreshManage(qc);
      onClose();
    } catch (e) { toastError(e); }
  };
  return (
    <Modal opened onClose={onClose} title={boat ? `Edit ${boat.name}` : "Add boat"}>
      <Stack>
        <TextInput label="Name" withAsterisk value={f.name} onChange={set("name")} error={!f.name.trim() ? "Required" : undefined} />
        <TextInput label="Sail number" withAsterisk value={f.sail_number} onChange={set("sail_number")} error={!f.sail_number.trim() ? "Required" : undefined} />
        <TextInput label="Design" value={f.design ?? ""} onChange={set("design")} />
        <TextInput label="Skipper" value={f.skipper ?? ""} onChange={set("skipper")} />
        <TextInput label="Home club" value={f.home_club ?? ""} onChange={set("home_club")} />
        <Checkbox label="Member of our club (may be exempt from some race fees)" checked={!!f.is_member}
          onChange={(e) => setF({ ...f, is_member: e.currentTarget.checked })} />
        <Select label="Default fleet" clearable value={f.default_fleet_id ? String(f.default_fleet_id) : null}
          data={fleets.map((x) => ({ value: String(x.id), label: x.name }))}
          onChange={(v) => setF({ ...f, default_fleet_id: v ? Number(v) : null })} />
        <Select label="Always rate as" description="e.g. ORCA boats always use their ORCA rating, whatever the start uses" clearable
          value={f.fixed_rating_type_id ? String(f.fixed_rating_type_id) : null}
          data={types.map((x) => ({ value: String(x.id), label: x.code }))}
          onChange={(v) => setF({ ...f, fixed_rating_type_id: v ? Number(v) : null })} />
        <TextInput label="Contact email (race committee only)" value={f.contact_email ?? ""} onChange={set("contact_email")} />
        <TextInput label="Contact phone (race committee only)" value={f.contact_phone ?? ""} onChange={set("contact_phone")} />
        <Button onClick={save} disabled={!f.name.trim() || !f.sail_number.trim()}>Save</Button>
      </Stack>
    </Modal>
  );
}

/** A boat's dated ratings. `defaultTypeId` / `defaultEffective` pre-select the type and date (e.g. from a race). */
export function RatingsModal({ boat, types, onClose, defaultTypeId, defaultEffective }: {
  boat: Boat; types: S["RatingTypeIO"][]; onClose: () => void; defaultTypeId?: number | null; defaultEffective?: string;
}) {
  const qc = useQueryClient();
  const [typeId, setTypeId] = useState<string | null>(
    String(defaultTypeId ?? boat.fixed_rating_type_id ?? types[0]?.id ?? ""),
  );
  const [value, setValue] = useState<number | "">("");
  const [eff, setEff] = useState(defaultEffective ?? new Date().toISOString().slice(0, 10));
  const [cert, setCert] = useState("");
  const [exp, setExp] = useState("");
  const type = types.find((t) => String(t.id) === typeId);
  const isTcf = type?.method === "tot";
  const valueError = value === "" ? "Required" : isTcf && value <= 0 ? "Must be greater than zero" : undefined;

  const add = async () => {
    try {
      await api(`/manage/boats/${boat.id}/ratings`, {
        method: "POST",
        body: { rating_type_id: Number(typeId), value, effective_from: eff, certificate: cert, expires: exp || null },
      });
      setValue("");
      await refreshManage(qc);
    } catch (e) { toastError(e); }
  };
  const del = async (id: number) => {
    try { await api(`/manage/ratings/${id}`, { method: "DELETE" }); await refreshManage(qc); } catch (e) { toastError(e); }
  };
  return (
    <Modal opened onClose={onClose} title={`${boat.name}: ratings`} size="lg">
      <Stack>
        <Table withTableBorder>
          <Table.Thead><Table.Tr><Table.Th>Type</Table.Th><Table.Th>Rating</Table.Th><Table.Th>Effective</Table.Th><Table.Th>Cert</Table.Th><Table.Th>Expires</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {boat.ratings.length === 0 && <Table.Tr><Table.Td colSpan={6}><Text size="sm" c="dimmed">No ratings yet.</Text></Table.Td></Table.Tr>}
            {boat.ratings.map((r) => (
              <Table.Tr key={r.id}>
                <Table.Td>{r.rating_type}</Table.Td><Table.Td>{r.value}</Table.Td><Table.Td>{r.effective_from}</Table.Td>
                <Table.Td>{r.certificate}</Table.Td><Table.Td>{r.expires ?? ""}</Table.Td>
                <Table.Td><Button size="compact-xs" color="red" variant="subtle" onClick={() => del(r.id)}>Delete</Button></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        <Text size="sm" c="dimmed">A re-rate adds a new dated row; older races keep using the rating in force on their date.</Text>
        <Group align="flex-start">
          <Select label="Type" withAsterisk w={100} allowDeselect={false} value={typeId} onChange={setTypeId} data={types.map((t) => ({ value: String(t.id), label: t.code }))} />
          <NumberInput label={isTcf ? "TCF" : "Rating (s/nm)"} withAsterisk w={120} decimalScale={4} value={value}
            error={valueError} onChange={(v) => setValue(v === "" ? "" : Number(v))} />
          <TextInput label="Effective from" withAsterisk type="date" value={eff} onChange={(e) => setEff(e.currentTarget.value)} error={!eff ? "Required" : undefined} />
          <TextInput label="Certificate" w={110} value={cert} onChange={(e) => setCert(e.currentTarget.value)} />
          <TextInput label="Expires" type="date" value={exp} onChange={(e) => setExp(e.currentTarget.value)} />
        </Group>
        <Group justify="flex-end">
          <Button onClick={add} disabled={!!valueError || !typeId || !eff}>Add rating</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
