import { Button, Card, Group, MultiSelect, NumberInput, Select, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, useGet, type S } from "../../api/client";
import { Query, toastError } from "../../components/bits";

export default function Courses() {
  const marks = useGet<S["MarkIO"][]>("/manage/marks");
  const courses = useGet<S["CourseOut"][]>("/manage/courses");
  const types = useGet<S["RatingTypeIO"][]>("/manage/rating-types");
  const qc = useQueryClient();
  const [mn, setMn] = useState("");
  const [lat, setLat] = useState<number | "">("");
  const [lon, setLon] = useState<number | "">("");
  const [cn, setCn] = useState("");
  const [ct, setCt] = useState<string | null>(null);
  const [legs, setLegs] = useState<string[]>([]);
  const [ov, setOv] = useState<number | "">("");

  const addMark = async () => {
    try {
      await api("/manage/marks", { method: "POST", body: { name: mn, lat, lon } });
      setMn(""); setLat(""); setLon("");
      await qc.invalidateQueries({ queryKey: ["/manage/marks"] });
    } catch (e) { toastError(e); }
  };
  const addCourse = async () => {
    try {
      await api("/manage/courses", {
        method: "POST",
        body: { name: cn, course_type_id: Number(ct), mark_ids: legs.map(Number), distance_override: ov === "" ? null : ov },
      });
      setCn(""); setLegs([]); setOv("");
      await qc.invalidateQueries({ queryKey: ["/manage/courses"] });
    } catch (e) { toastError(e); }
  };

  return (
    <Stack>
      <Title order={2}>Marks</Title>
      <Query q={marks}>
        {(list) => (
          <Table withTableBorder maw={600}>
            <Table.Thead><Table.Tr><Table.Th>Mark</Table.Th><Table.Th>Lat</Table.Th><Table.Th>Lon</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{list.map((m) => <Table.Tr key={m.id}><Table.Td>{m.name}</Table.Td><Table.Td>{m.lat}</Table.Td><Table.Td>{m.lon}</Table.Td></Table.Tr>)}</Table.Tbody>
          </Table>
        )}
      </Query>
      <Group align="flex-end">
        <TextInput label="Name" value={mn} onChange={(e) => setMn(e.currentTarget.value)} />
        <NumberInput label="Latitude" w={130} decimalScale={5} value={lat} onChange={(v) => setLat(v === "" ? "" : Number(v))} />
        <NumberInput label="Longitude" w={130} decimalScale={5} value={lon} onChange={(v) => setLon(v === "" ? "" : Number(v))} />
        <Button onClick={addMark} disabled={!mn || lat === "" || lon === ""}>Add mark</Button>
      </Group>

      <Title order={2} mt="lg">Courses</Title>
      <Query q={courses}>
        {(list) => (
          <Table withTableBorder>
            <Table.Thead><Table.Tr><Table.Th>Course</Table.Th><Table.Th>Type</Table.Th><Table.Th ta="right">Distance (nm)</Table.Th><Table.Th>Route</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {list.map((c) => (
                <Table.Tr key={c.id}>
                  <Table.Td>{c.name}</Table.Td><Table.Td>{c.course_type}</Table.Td>
                  <Table.Td ta="right">{Number(c.distance_nm).toFixed(2)}{c.distance_override !== null && <Text span size="xs" c="dimmed"> (entered)</Text>}</Table.Td>
                  <Table.Td>{c.description || c.mark_ids.map((id) => marks.data?.find((m) => m.id === id)?.name).join(" → ")}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Query>
      <Card withBorder>
        <Stack gap="xs">
          <Text fw={600}>New course</Text>
          <Group align="flex-end">
            <TextInput label="Name" withAsterisk value={cn} onChange={(e) => setCn(e.currentTarget.value)} />
            <Select label="Course type" withAsterisk w={110} value={ct} onChange={setCt} data={(types.data ?? []).map((t) => ({ value: String(t.id), label: t.code }))} />
            <NumberInput label="Distance override (nm)" w={170} value={ov} onChange={(v) => setOv(v === "" ? "" : Number(v))} />
          </Group>
          <MultiSelect label="Marks (in rounding order; pick repeats via separate courses)" searchable value={legs} onChange={setLegs}
            data={(marks.data ?? []).map((m) => ({ value: String(m.id), label: m.name }))} />
          <Text size="xs" c="dimmed">Distance is computed from the mark positions in the order chosen unless you enter one.</Text>
          {legs.length < 2 && ov === "" && <Text size="sm" c="orange">Pick at least two marks, or enter the distance.</Text>}
          <Button onClick={addCourse} disabled={!cn.trim() || !ct || (legs.length < 2 && ov === "") || (ov !== "" && ov <= 0)} w={160}>Add course</Button>
        </Stack>
      </Card>
    </Stack>
  );
}
