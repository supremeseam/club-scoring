import { Alert, Button, Card, Center, List, PasswordInput, Stack, Text, Title } from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, useGet, type SiteConfig } from "../../api/client";
import { useAuth } from "../../auth";
import { toastOk } from "../../components/bits";

/** Choose a new password. Also where someone holding a temporary password is sent first. */
export default function ChangePassword() {
  const { user, refresh } = useAuth();
  const cfg = useGet<SiteConfig>("/config");
  const nav = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const min = cfg.data?.password_min_length ?? 15;
  const max = cfg.data?.password_max_length ?? 256;
  const forced = !!user?.must_change_password;
  const mismatch = confirm !== "" && confirm !== next;
  const ok = current !== "" && next.length >= min && next.length <= max && next === confirm;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/change-password", { method: "POST", body: { current_password: current, new_password: next } });
      toastOk("Password changed");
      await refresh();
      nav("/rc");
    } catch (ex) {
      setError(ex instanceof Error ? ex.message : "Could not change the password");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Center pt="xl">
      <Card w="100%" maw={460} p="xl" shadow="md" withBorder>
        <form onSubmit={submit}>
          <Stack>
            <Title order={3}>{forced ? "Choose your own password" : "Change password"}</Title>
            {forced && (
              <Alert color="blue">
                You signed in with a temporary password. Choose your own to continue.
              </Alert>
            )}
            {error && <Alert color="red">{error}</Alert>}
            <PasswordInput label={forced ? "Temporary password" : "Current password"} autoComplete="current-password"
              value={current} onChange={(e) => setCurrent(e.currentTarget.value)} withAsterisk maxLength={max} />
            <PasswordInput label="New password" autoComplete="new-password" value={next} withAsterisk maxLength={max}
              onChange={(e) => setNext(e.currentTarget.value)}
              error={next !== "" && next.length < min ? `At least ${min} characters (${next.length} so far)` : undefined} />
            <PasswordInput label="Type the new password again" autoComplete="new-password" value={confirm} withAsterisk
              maxLength={max} onChange={(e) => setConfirm(e.currentTarget.value)}
              error={mismatch ? "The two passwords don't match" : undefined} />
            <Text size="sm" c="dimmed">A long phrase works best, for example four unrelated words.</Text>
            <List size="sm" c="dimmed" spacing={2}>
              <List.Item>At least {min} characters; spaces and any characters are fine, and pasting is allowed.</List.Item>
              <List.Item>No need for capitals, numbers or symbols, and no need to change it regularly.</List.Item>
              <List.Item>Not your username, name or the club's name, and nothing obvious or commonly used.</List.Item>
            </List>
            <Button type="submit" loading={busy} disabled={!ok} fullWidth size="md">Save new password</Button>
          </Stack>
        </form>
      </Card>
    </Center>
  );
}
