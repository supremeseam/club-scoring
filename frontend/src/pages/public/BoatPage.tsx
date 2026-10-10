import { Anchor, Stack, Table, Text, Title } from "@mantine/core";
import { Link, useParams } from "react-router-dom";
import { useGet, type S } from "../../api/client";
import { Query } from "../../components/bits";
import { fmtDate, fmtPoints } from "../../lib/time";

export default function BoatPage() {
  const { id } = useParams();
  const q = useGet<S["BoatHistory"]>(`/boats/${id}/history`);
  return (
    <Query q={q}>
      {({ boat, rows }) => (
        <Stack>
          <Title order={2}>{boat.name}</Title>
          <Text>
            Sail {boat.sail_number} {boat.design && `· ${boat.design}`} {boat.skipper && `· ${boat.skipper}`}
          </Text>
          <Table.ScrollContainer minWidth={560}>
            <Table striped withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Date</Table.Th>
                  <Table.Th>Series</Table.Th>
                  <Table.Th>Race</Table.Th>
                  <Table.Th ta="right">Rating</Table.Th>
                  <Table.Th ta="right">Corrected</Table.Th>
                  <Table.Th ta="right">Pts</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.map((r) => (
                  <Table.Tr key={`${r.series_id}-${r.race_id}`}>
                    <Table.Td>{fmtDate(r.date)}</Table.Td>
                    <Table.Td><Anchor component={Link} to={`/series/${r.series_id}`}>{r.series_name}</Anchor></Table.Td>
                    <Table.Td><Anchor component={Link} to={`/races/${r.race_id}`}>R{r.race_number}</Anchor></Table.Td>
                    <Table.Td ta="right">{r.rating ?? ""} {r.rating ? r.rating_type : ""}</Table.Td>
                    <Table.Td ta="right">{r.corrected ?? ""}</Table.Td>
                    <Table.Td ta="right">{fmtPoints(r.points)} {r.status ?? ""}{r.note ? <Text size="xs" c="dimmed">{r.note}</Text> : null}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Stack>
      )}
    </Query>
  );
}
