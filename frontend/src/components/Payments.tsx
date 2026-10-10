import { Badge, Button, Group, NumberInput, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, useGet, type S } from "../api/client";
import { Query, toastError, toastOk } from "./bits";

type Series = S["SeriesEditor"];

/** What a boat owes by default: the member price for members when the series sets one. */
export function defaultFee(series: Series, member: boolean, forRace: boolean): number {
  const member_fee = forRace ? series.member_race_fee : series.member_series_fee;
  const normal = forRace ? series.race_fee : series.series_fee;
  return Number(member && member_fee !== null && member_fee !== undefined ? member_fee : (normal ?? 0));
}

export function PaymentsPanel({ series }: { series: Series }) {
  const qc = useQueryClient();
  const payments = useGet<S["PaymentOut"][]>(`/manage/series/${series.id}/payments`);
  const entries = useGet<S["EntryIO"][]>(`/manage/series/${series.id}/entries`);
  const boats = useGet<S["BoatOut"][]>("/manage/boats");
  const races = useGet<S["RaceEditor"][]>(`/manage/series/${series.id}/races`);
  const [boat, setBoat] = useState<string | null>(null);
  const [scope, setScope] = useState<string>("series");
  const [amount, setAmount] = useState<number | "">("");
  const [paidOn, setPaidOn] = useState(new Date().toISOString().slice(0, 10));
  const [method, setMethod] = useState("");

  const refresh = () => qc.invalidateQueries({ queryKey: [`/manage/series/${series.id}/payments`] });
  const boatObj = boats.data?.find((b) => String(b.id) === boat);
  const suggested = defaultFee(series, !!boatObj?.is_member, scope !== "series");

  const record = async () => {
    try {
      await api(`/manage/series/${series.id}/payments`, {
        method: "POST",
        body: {
          boat_id: Number(boat), race_id: scope === "series" ? null : Number(scope),
          amount: amount === "" ? null : amount, paid_on: paidOn, method,
        },
      });
      toastOk("Payment recorded");
      setAmount("");
      await refresh();
    } catch (e) { toastError(e); }
  };
  const remove = async (id: number) => {
    try { await api(`/manage/payments/${id}`, { method: "DELETE" }); await refresh(); } catch (e) { toastError(e); }
  };

  const raceOptions = (races.data ?? []).map((r) => ({ value: String(r.id), label: `Race ${r.number}${r.members_free ? " (members free)" : ""}` }));
  return (
    <Stack gap="xs">
      <Text fw={600}>Payments</Text>
      <Text size="xs" c="dimmed">
        Visible to editors only. {series.require_payment
          ? "Boats are scored only in races they paid for (or the whole series). Others show as guests."
          : "Payment is not required to be scored in this series; turn on “Require payment” in the series settings to enforce it."}
      </Text>
      <Query q={payments}>
        {(list) => (
          <>
            <Table.ScrollContainer minWidth={520}>
              <Table withTableBorder striped>
                <Table.Thead>
                  <Table.Tr><Table.Th>Boat</Table.Th><Table.Th>Paid for</Table.Th><Table.Th ta="right">Amount</Table.Th><Table.Th>Date</Table.Th><Table.Th>How</Table.Th><Table.Th /></Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {list.length === 0 && <Table.Tr><Table.Td colSpan={6}><Text size="sm" c="dimmed">No payments recorded.</Text></Table.Td></Table.Tr>}
                  {list.map((p) => (
                    <Table.Tr key={p.id}>
                      <Table.Td>{p.boat}</Table.Td>
                      <Table.Td>{p.race_number ? `Race ${p.race_number}` : <Badge size="sm">Whole series</Badge>}</Table.Td>
                      <Table.Td ta="right">{Number(p.amount).toFixed(2)}</Table.Td>
                      <Table.Td>{p.paid_on}</Table.Td>
                      <Table.Td>{p.method}</Table.Td>
                      <Table.Td><Button size="compact-xs" color="red" variant="subtle" onClick={() => remove(p.id)}>Delete</Button></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            <PaidGrid series={series} payments={list} entries={entries.data ?? []} boats={boats.data ?? []} races={races.data ?? []} />
            <Unpaid series={series} payments={list} entries={entries.data ?? []} boats={boats.data ?? []} />
          </>
        )}
      </Query>
      <Group align="flex-end" gap="xs">
        <Select label="Boat" searchable w={200} value={boat} onChange={setBoat}
          data={(entries.data ?? []).map((e) => {
            const b = boats.data?.find((x) => x.id === e.boat_id);
            return { value: String(e.boat_id), label: b ? `${b.name}${b.is_member ? " (member)" : ""}` : String(e.boat_id) };
          })} />
        <Select label="For" w={170} allowDeselect={false} value={scope} onChange={(v) => setScope(v ?? "series")}
          data={[{ value: "series", label: "Whole series" }, ...raceOptions]} />
        <NumberInput label="Amount" w={110} decimalScale={2} value={amount} placeholder={String(suggested)}
          onChange={(v) => setAmount(v === "" ? "" : Number(v))} />
        <TextInput label="Date paid" type="date" value={paidOn} onChange={(e) => setPaidOn(e.currentTarget.value)} />
        <TextInput label="How (cash, check...)" w={140} value={method} onChange={(e) => setMethod(e.currentTarget.value)} />
        <Button onClick={record} disabled={!boat}>Record payment</Button>
      </Group>
    </Stack>
  );
}

function Unpaid({ series, payments, entries, boats }: {
  series: Series; payments: S["PaymentOut"][]; entries: S["EntryIO"][]; boats: S["BoatOut"][];
}) {
  if (!series.require_payment) return null;
  const paid = new Set(payments.map((p) => p.boat_id));
  const names = entries.filter((e) => !paid.has(e.boat_id)).map((e) => boats.find((b) => b.id === e.boat_id)?.name).filter(Boolean);
  if (!names.length) return <Text size="sm" c="teal">Every entered boat has a payment recorded.</Text>;
  return <Text size="sm" c="orange">No payment yet (scored as guests): {names.join(", ")}</Text>;
}

/** Who is covered for which race. A series payment covers every race; members race free where ticked. */
function PaidGrid({ series, payments, entries, boats, races }: {
  series: Series; payments: S["PaymentOut"][]; entries: S["EntryIO"][]; boats: S["BoatOut"][]; races: S["RaceEditor"][];
}) {
  if (!entries.length || !races.length) return null;
  const sorted = [...races].sort((a, b) => a.number - b.number);
  return (
    <Stack gap={4}>
      <Text size="sm" fw={600}>Paid, race by race</Text>
      <Table.ScrollContainer minWidth={420}>
        <Table withTableBorder striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Boat</Table.Th><Table.Th>Series</Table.Th>
              {sorted.map((r) => <Table.Th key={r.id} ta="center">R{r.number}</Table.Th>)}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {entries.map((e) => {
              const b = boats.find((x) => x.id === e.boat_id);
              const mine = payments.filter((p) => p.boat_id === e.boat_id);
              const wholeSeries = mine.some((p) => p.race_id === null);
              return (
                <Table.Tr key={e.boat_id}>
                  <Table.Td>{b?.name}{b?.is_member ? " (member)" : ""}</Table.Td>
                  <Table.Td ta="center">{wholeSeries ? <Text c="teal" fw={700}>{"\u2713"}</Text> : <Text c="dimmed">{"\u2014"}</Text>}</Table.Td>
                  {sorted.map((r) => {
                    const direct = mine.some((p) => p.race_id === r.id);
                    const free = !!b?.is_member && r.members_free;
                    const ok = wholeSeries || direct || free;
                    return (
                      <Table.Td key={r.id} ta="center" title={wholeSeries ? "covered by the series payment" : free ? "member, race free" : direct ? "paid for this race" : "unpaid"}>
                        {ok ? <Text c={direct ? "teal" : "dimmed"} fw={direct ? 700 : 400}>{"\u2713"}</Text> : series.require_payment ? <Text c="red">{"\u00d7"}</Text> : <Text c="dimmed">{"\u2014"}</Text>}
                      </Table.Td>
                    );
                  })}
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Text size="xs" c="dimmed">{"\u2713"} paid or covered ({"\u2713"} in bold = paid for that race; grey = covered by the series payment or a members-free race). {"\u00d7"} = unpaid.</Text>
    </Stack>
  );
}
