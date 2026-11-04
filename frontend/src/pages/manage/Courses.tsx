import { ActionIcon, Button, Card, Group, NumberInput, Select, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, useGet, type S } from "../../api/client";
import { Query, toastError, toastOk } from "../../components/bits";

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
  const [pick, setPick] = useState<string | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [desc, setDesc] = useState("");
  const formRef = useRef<HTMLDivElement>(null);
  const startEdit = (c: S["CourseOut"]) => {
    setEditing(c.id);
    setCn(c.name); setCt(String(c.course_type_id)); setLegs(c.mark_ids.map(String));
    setOv(c.distance_override ?? ""); setDesc(c.description ?? "");
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const resetForm = () => { setEditing(null); setCn(""); setCt(null); setLegs([]); setOv(""); setDesc(""); };
  const markName = (id: string) => marks.data?.find((m) => String(m.id) === id)?.name ?? id;
  const addLeg = (id: string | null) => { if (id) { setLegs([...legs, id]); setPick(null); } };
  const moveLeg = (i: number, d: -1 | 1) => {
    const j = i + d;
    if (j < 0 || j >= legs.length) return;
    const next = [...legs];
    [next[i], next[j]] = [next[j], next[i]];
    setLegs(next);
  };

  const [editingMark, setEditingMark] = useState<number | null>(null);
  const resetMark = () => { setEditingMark(null); setMn(""); setLat(""); setLon(""); };
  const saveMark = async () => {
    try {
      await api(editingMark ? `/manage/marks/${editingMark}` : "/manage/marks", { method: editingMark ? "PUT" : "POST", body: { name: mn, lat, lon } });
      toastOk(editingMark ? "Mark saved" : "Mark added");
      resetMark();
      await qc.invalidateQueries({ queryKey: ["/manage/marks"] });
      await qc.invalidateQueries({ queryKey: ["/manage/courses"] });      // distances may have changed
    } catch (e) { toastError(e); }
  };
  const deleteMark = async (m: S["MarkIO"]) => {
    if (!window.confirm(`Delete the mark "${m.name}"?`)) return;
    try {
      await api(`/manage/marks/${m.id}`, { method: "DELETE" });
      if (editingMark === m.id) resetMark();
      await qc.invalidateQueries({ queryKey: ["/manage/marks"] });
    } catch (e) { toastError(e); }
  };
  const deleteCourse = async (c: S["CourseOut"]) => {
    if (!window.confirm(`Delete the course "${c.name}"?`)) return;
    try {
      await api(`/manage/courses/${c.id}`, { method: "DELETE" });
      if (editing === c.id) resetForm();
      await qc.invalidateQueries({ queryKey: ["/manage/courses"] });
    } catch (e) { toastError(e); }
  };
  const saveCourse = async () => {
    try {
      await api(editing ? `/manage/courses/${editing}` : "/manage/courses", {
        method: editing ? "PUT" : "POST",
        body: { name: cn, course_type_id: Number(ct), mark_ids: legs.map(Number), distance_override: ov === "" ? null : ov, description: desc },
      });
      toastOk(editing ? "Course saved" : "Course added");
      resetForm();
      await qc.invalidateQueries({ queryKey: ["/manage/courses"] });
    } catch (e) { toastError(e); }
  };

  return (
    <Stack>
      <Title order={2}>Marks</Title>
      <Query q={marks}>
        {(list) => (
          <Table withTableBorder maw={600}>
            <Table.Thead><Table.Tr><Table.Th>Mark</Table.Th><Table.Th>Lat</Table.Th><Table.Th>Lon</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>{list.map((m) => <Table.Tr key={m.id}><Table.Td>{m.name}</Table.Td><Table.Td>{m.lat}</Table.Td><Table.Td>{m.lon}</Table.Td>
              <Table.Td>
                <Group gap={4} wrap="nowrap">
                  <Button size="compact-xs" variant="default" onClick={() => { setEditingMark(m.id ?? null); setMn(m.name); setLat(m.lat); setLon(m.lon); }}>Edit</Button>
                  <Button size="compact-xs" variant="subtle" color="red" onClick={() => deleteMark(m)}>Delete</Button>
                </Group>
              </Table.Td></Table.Tr>)}</Table.Tbody>
          </Table>
        )}
      </Query>
      <Group align="flex-end">
        <TextInput label="Name" value={mn} onChange={(e) => setMn(e.currentTarget.value)} />
        <NumberInput label="Latitude" w={130} decimalScale={5} value={lat} onChange={(v) => setLat(v === "" ? "" : Number(v))} />
        <NumberInput label="Longitude" w={130} decimalScale={5} value={lon} onChange={(v) => setLon(v === "" ? "" : Number(v))} />
        <Button onClick={saveMark} disabled={!mn.trim() || lat === "" || lon === ""}>{editingMark ? "Save mark" : "Add mark"}</Button>
        {editingMark && <Button variant="default" onClick={resetMark}>Cancel</Button>}
      </Group>
      {editingMark && <Text size="xs" c="orange">Moving a mark changes the distance of every course through it and rescores races already sailed on those courses.</Text>}

      <Title order={2} mt="lg">Courses</Title>
      <Query q={courses}>
        {(list) => (
          <Table withTableBorder>
            <Table.Thead><Table.Tr><Table.Th>Course</Table.Th><Table.Th>Type</Table.Th><Table.Th ta="right">Distance (nm)</Table.Th><Table.Th>Route</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>
              {list.map((c) => (
                <Table.Tr key={c.id}>
                  <Table.Td>{c.name}</Table.Td><Table.Td>{c.course_type}</Table.Td>
                  <Table.Td ta="right">{Number(c.distance_nm) > 0 ? Number(c.distance_nm).toFixed(2) : <Text span size="sm" c="dimmed">none yet</Text>}{c.distance_override !== null && <Text span size="xs" c="dimmed"> (entered)</Text>}</Table.Td>
                  <Table.Td>{c.description || c.mark_ids.map((id) => marks.data?.find((m) => m.id === id)?.name).join(" → ")}</Table.Td>
                  <Table.Td><Group gap={4} wrap="nowrap">
                    <Button size="compact-xs" variant="default" onClick={() => startEdit(c)}>Edit</Button>
                    <Button size="compact-xs" variant="subtle" color="red" onClick={() => deleteCourse(c)}>Delete</Button>
                  </Group></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Query>
      <Card withBorder ref={formRef}>
        <Stack gap="xs">
          <Text fw={600}>{editing ? `Edit course: ${cn || "(no name)"}` : "New course"}</Text>
          {editing && <Text size="sm" c="orange">Changing the marks or distance rescores races already sailed on this course (races with their own distance are not affected).</Text>}
          <Group align="flex-end">
            <TextInput label="Name" withAsterisk value={cn} onChange={(e) => setCn(e.currentTarget.value)} />
            <Select label="Course type" withAsterisk w={110} value={ct} onChange={setCt} data={(types.data ?? []).map((t) => ({ value: String(t.id), label: t.code }))} />
            <NumberInput label="Distance override (nm)" w={170} value={ov} onChange={(v) => setOv(v === "" ? "" : Number(v))} />
          </Group>
          <Stack gap={4}>
            <Text size="sm" fw={500}>Marks in rounding order (optional)</Text>
            {legs.length === 0 && <Text size="sm" c="dimmed">No marks yet. A course can be just a name; you then enter the distance on the race.</Text>}
            {legs.map((id, i) => (
              <Group key={i} gap="xs" wrap="nowrap">
                <Text size="sm" w={24} c="dimmed">{i + 1}.</Text>
                <Text size="sm" w={180}>{markName(id)}</Text>
                <ActionIcon variant="subtle" aria-label="Move up" disabled={i === 0} onClick={() => moveLeg(i, -1)}>{"↑"}</ActionIcon>
                <ActionIcon variant="subtle" aria-label="Move down" disabled={i === legs.length - 1} onClick={() => moveLeg(i, 1)}>{"↓"}</ActionIcon>
                <ActionIcon variant="subtle" color="red" aria-label="Remove mark" onClick={() => setLegs(legs.filter((_, k) => k !== i))}>{"×"}</ActionIcon>
              </Group>
            ))}
            <Group align="flex-end" gap="xs">
              <Select label="Add a mark" placeholder="Pick a mark to add next" searchable clearable w={260} value={pick} onChange={addLeg}
                data={(marks.data ?? []).map((m) => ({ value: String(m.id), label: m.name }))} />
              {legs.length > 0 && <Button variant="light" onClick={() => addLeg(legs[0])}>Finish at the first mark ({markName(legs[0])})</Button>}
            </Group>
            <Text size="xs" c="dimmed">A mark can be used as often as you like, for example to start and finish at the same mark.</Text>
          </Stack>
          <TextInput label="Route description (optional)" description="Shown in the course list instead of the mark names" maxLength={300} value={desc} onChange={(e) => setDesc(e.currentTarget.value)} />
          <Text size="xs" c="dimmed">Distance is computed from the mark positions in the order above unless you enter one.</Text>
          <Group>
            <Button onClick={saveCourse} disabled={!cn.trim() || !ct || (ov !== "" && ov <= 0)} w={160}>{editing ? "Save changes" : "Add course"}</Button>
            {editing && <Button variant="default" onClick={resetForm}>Cancel</Button>}
          </Group>
        </Stack>
      </Card>
    </Stack>
  );
}
