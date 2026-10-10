import { Alert, Button, Card, Center, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, type S } from "../../api/client";
import { useAuth } from "../../auth";
import { Burgee, useSite } from "../../components/Brand";

export default function Login() {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [otp, setO] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const { refresh, expired, clearExpired } = useAuth();
  const { data: cfg } = useSite();
  const nav = useNavigate();
  const loc = useLocation();
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api("/auth/csrf");
      const me = await api<S["Me"]>("/auth/login", { method: "POST", body: { username, password, otp } });
      clearExpired();
      await refresh();
      // a temporary password must be replaced before anything else
      nav(me.must_change_password ? "/change-password" : ((loc.state as { from?: string } | null)?.from ?? "/rc"));
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Center pt="xl">
      <Card w="100%" maw={400} p="xl" shadow="md" withBorder>
        <form onSubmit={submit}>
          <Stack>
            <Stack align="center" gap={4}>
              <Burgee height={56} />
              <Title order={3}>Race committee login</Title>
              <Text size="sm" c="dimmed">{cfg?.app_name}</Text>
            </Stack>
            {expired && !err && <Alert color="blue">Your session ended. Please sign in again.</Alert>}
            {err && <Alert color="red">{err}</Alert>}
            <TextInput label="Username" autoComplete="username" value={username} onChange={(e) => setU(e.currentTarget.value)} required />
            <PasswordInput label="Password" autoComplete="current-password" maxLength={256} value={password} onChange={(e) => setP(e.currentTarget.value)} required />
            {cfg?.require_2fa && (
              <TextInput label="Authentication code" description="6-digit code from your authenticator app" inputMode="numeric"
                autoComplete="one-time-code" value={otp} onChange={(e) => setO(e.currentTarget.value)} />
            )}
            <Button type="submit" loading={busy} fullWidth size="md">Log in</Button>
            <Text size="xs" c="dimmed" ta="center">Forgot your password? Ask a site administrator to reset it.</Text>
          </Stack>
        </form>
      </Card>
    </Center>
  );
}
