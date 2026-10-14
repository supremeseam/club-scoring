import { Alert, Button, Card, PasswordInput, Select, SimpleGrid, Stack, Text, Textarea, TextInput, Title } from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, useGet } from "../../api/client";
import { useAuth } from "../../auth";
import type { Options } from "../../lib/crew";

const HONEY = { position: "absolute", left: "-9999px" } as const;

function CrewAccount() {
  const { refresh } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ username: "", password: "", name: "", email: "", website: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.currentTarget.value });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api("/auth/csrf");
      await api("/crew/register", { method: "POST", body: f });
      await refresh();
      nav("/crew/my");
    } catch (ex) { setErr(ex instanceof Error ? ex.message : "Could not register"); } finally { setBusy(false); }
  };
  return (
    <Card withBorder p="lg">
      <form onSubmit={submit}>
        <Stack>
          <Title order={4}>Crew account (optional)</Title>
          <Text size="sm" c="dimmed">You never need one to sign up. An account lets you see answers and withdraw from any device.</Text>
          {err && <Alert color="red">{err}</Alert>}
          <TextInput label="Your name" required maxLength={80} value={f.name} onChange={set("name")} />
          <TextInput label="Email" type="email" required value={f.email} onChange={set("email")} />
          <TextInput label="Username" required autoComplete="username" value={f.username} onChange={set("username")} />
          <PasswordInput label="Password" required autoComplete="new-password" maxLength={256} value={f.password} onChange={set("password")}
            description="15 or more characters. A few ordinary words work well." />
          <div style={HONEY} aria-hidden="true"><label>Website<input tabIndex={-1} autoComplete="off" value={f.website} onChange={set("website")} /></label></div>
          <Button type="submit" loading={busy}>Create crew account</Button>
        </Stack>
      </form>
    </Card>
  );
}

function SkipperRequest() {
  const opts = useGet<Options>("/crew/options");
  const [f, setF] = useState({ name: "", email: "", boat_text: "", message: "", website: "" });
  const [boat, setBoat] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.currentTarget.value });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api("/auth/csrf");
      await api("/crew/skipper-requests", { method: "POST", body: { ...f, boat_id: boat ? Number(boat) : null } });
      setSent(true);
    } catch (ex) { setErr(ex instanceof Error ? ex.message : "Could not send"); } finally { setBusy(false); }
  };
  return (
    <Card withBorder p="lg">
      {sent ? (
        <Alert color="green" title="Request sent">The race committee will set up your login and give you a temporary password.</Alert>
      ) : (
        <form onSubmit={submit}>
          <Stack>
            <Title order={4}>Skipper login</Title>
            <Text size="sm" c="dimmed">Skippers post crew openings for their own boat. The race committee approves each login and links it to your boat.</Text>
            {err && <Alert color="red">{err}</Alert>}
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <TextInput label="Your name" required maxLength={80} value={f.name} onChange={set("name")} />
              <TextInput label="Email" type="email" required value={f.email} onChange={set("email")} />
            </SimpleGrid>
            <Select label="Your boat" searchable clearable value={boat} onChange={setBoat}
              data={(opts.data?.boats ?? []).map((b) => ({ value: String(b.id), label: `${b.name} (${b.sail_number})` }))} />
            {!boat && <TextInput label="Not listed? Boat name and sail number" maxLength={120} value={f.boat_text} onChange={set("boat_text")} />}
            <Textarea label="Anything the committee should know (optional)" maxLength={300} autosize minRows={2} value={f.message} onChange={set("message")} />
            <div style={HONEY} aria-hidden="true"><label>Website<input tabIndex={-1} autoComplete="off" value={f.website} onChange={set("website")} /></label></div>
            <Button type="submit" loading={busy} disabled={!boat && !f.boat_text.trim()}>Request a skipper login</Button>
          </Stack>
        </form>
      )}
    </Card>
  );
}

export default function CrewJoin() {
  return (
    <Stack>
      <Title order={2}>Skipper and crew accounts</Title>
      <SimpleGrid cols={{ base: 1, md: 2 }} style={{ alignItems: "start" }}>
        <SkipperRequest />
        <CrewAccount />
      </SimpleGrid>
    </Stack>
  );
}
