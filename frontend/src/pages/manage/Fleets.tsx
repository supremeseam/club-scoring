import { ActionIcon, Button, Card, Group, NumberInput, Select, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, useGet, type S } from "../../api/client";
import { Query, toastError } from "../../components/bits";

export default function Fleets() {
  const fleets = useGet<S["FleetIO"][]>("/manage/fleets");
  const types = useGet<S["RatingTypeIO"][]>("/manage/rating-types");
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [tname, setTname] = useState("");
  const [fb, setFb] = useState<string | null>(null);
  const [off, setOff] = useState<number | "">(0);
  const [method, setMethod] = useState<string | null>("tod");

  /** Swap a fleet with its neighbour, then renumber 1..n so the start order is always tidy. */
  const move = async (index: number, delta: -1 | 1) => {
    const list = [...(fleets.data ?? [])];
    const j = index + delta;
    if (j < 0 || j >= list.length) return;
    [list[index], list[j]] = [list[j], list[index]];
    try {
      await Promise.all(list.map((f, i) => (f.display_order === i + 1 ? null :
        api(`/manage/fleets/${f.id}`, { method: "PUT", body: { ...f, display_order: i + 1 } }))));
      await qc.invalidateQueries({ queryKey: ["/manage/fleets"] });
    } catch (e) { toastError(e); }
  };

  const addFleet = async () => {
    try {
      await api("/manage/fleets", { method: "POST", body: { name, display_order: (fleets.data?.length ?? 0) + 1 } });
      setName("");
      await qc.invalidateQueries({ queryKey: ["/manage/fleets"] });
    } catch (e) { toastError(e); }
  };
  const addType = async () => {
    try {
      await api("/manage/rating-types", {
        method: "POST",
        body: { code: code.toUpperCase(), name: tname, display_order: (types.data?.length ?? 0) + 1,
                fallback_type_id: fb ? Number(fb) : null, fallback_offset: off === "" ? 0 : off, method: method ?? "tod" },
      });
      setCode(""); setTname(""); setFb(null); setOff(0);
      await qc.invalidateQueries({ queryKey: ["/manage/rating-types"] });
    } catch (e) { toastError(e); }
  };
  return (
    <Stack>
      <Title order={2}>Fleets</Title>
      <Query q={fleets}>
        {(list) => (
          <Stack gap="xs">
            <Text size="sm" c="dimmed">Start order. Fleets are listed in this order on results, standings, the RC screen and printed sheets.</Text>
            <Table withTableBorder maw={500}>
              <Table.Tbody>
                {list.map((f, i) => (
                  <Table.Tr key={f.id}>
                    <Table.Td w={40} c="dimmed">{i + 1}</Table.Td>
                    <Table.Td>{f.name}</Table.Td>
                    <Table.Td w={90}>
                      <Group gap={4} wrap="nowrap">
                        <ActionIcon variant="subtle" aria-label={`Move ${f.name} up`} disabled={i === 0} onClick={() => move(i, -1)}>{"\u2191"}</ActionIcon>
                        <ActionIcon variant="subtle" aria-label={`Move ${f.name} down`} disabled={i === list.length - 1} onClick={() => move(i, 1)}>{"\u2193"}</ActionIcon>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Stack>
        )}
      </Query>
      <Group align="flex-end">
        <TextInput label="New fleet" value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Button onClick={addFleet} disabled={!name}>Add fleet</Button>
      </Group>

      <Title order={2} mt="lg">Rating types</Title>
      <Query q={types}>
        {(list) => (
          <Table withTableBorder maw={700}>
            <Table.Thead><Table.Tr><Table.Th>Code</Table.Th><Table.Th>Name</Table.Th><Table.Th>Method</Table.Th><Table.Th>Fallback when missing</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {list.map((t) => {
                const f = list.find((x) => x.id === t.fallback_type_id);
                return (
                  <Table.Tr key={t.id}>
                    <Table.Td>{t.code}</Table.Td><Table.Td>{t.name}</Table.Td>
                    <Table.Td>{t.method === "tot" ? "time-on-time (TCF)" : "time-on-distance (s/nm)"}</Table.Td>
                    <Table.Td>{f ? `${f.code} ${t.fallback_offset >= 0 ? "+" : "−"} ${Math.abs(t.fallback_offset)} s/nm` : "none (RC must enter a rating)"}</Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        )}
      </Query>
      <Card withBorder maw={700}>
        <Group align="flex-end">
          <TextInput label="Code" w={90} value={code} onChange={(e) => setCode(e.currentTarget.value)} />
          <TextInput label="Name" value={tname} onChange={(e) => setTname(e.currentTarget.value)} />
          <Select label="Method" w={200} allowDeselect={false} value={method} onChange={setMethod}
            data={[{ value: "tod", label: "Time-on-distance" }, { value: "tot", label: "Time-on-time (TCF)" }]} />
          <Select label="Fallback type" clearable w={130} value={fb} onChange={setFb}
            data={(types.data ?? []).map((t) => ({ value: String(t.id), label: t.code }))} />
          <NumberInput label="Offset s/nm" w={110} value={off} onChange={(v) => setOff(v === "" ? "" : Number(v))} />
          <Button onClick={addType} disabled={!code || !tname}>Add type</Button>
        </Group>
      </Card>
    </Stack>
  );
}
