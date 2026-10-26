import { Anchor, AppShell, Badge, Button, Group, Menu, Text } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { Link, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, authSettings } from "./api/client";
import { clearTokens } from "./lib/tokens";
import { RequireEditor, RequireSignedIn, useAuth } from "./auth";
import { Burgee, SiteFooter, useSite } from "./components/Brand";
import Boats from "./pages/manage/Boats";
import CrewAdmin from "./pages/manage/CrewAdmin";
import Courses from "./pages/manage/Courses";
import Fleets from "./pages/manage/Fleets";
import SeriesManage from "./pages/manage/SeriesManage";
import MySignups from "./pages/crew/MySignups";
import SkipperHome from "./pages/crew/SkipperHome";
import BoatPage from "./pages/public/BoatPage";
import CrewBoard from "./pages/public/CrewBoard";
import CrewJoin from "./pages/public/CrewJoin";
import ChangePassword from "./pages/public/ChangePassword";
import Login from "./pages/public/Login";
import RacePage from "./pages/public/RacePage";
import SeriesList from "./pages/public/SeriesList";
import SeriesPage from "./pages/public/SeriesPage";
import RcHome from "./pages/rc/RcHome";
import RcRace from "./pages/rc/RcRace";

const LINKS: [string, string][] = [
  ["/rc", "Race committee"],
  ["/manage/series", "Series"],
  ["/manage/boats", "Boats & ratings"],
  ["/manage/fleets", "Fleets & rating types"],
  ["/manage/courses", "Marks & courses"],
  ["/manage/crew", "Crew board"],
];
const SKIPPER_LINKS: [string, string][] = [["/skipper", "My boat's crew"]];
const CREW_LINKS: [string, string][] = [["/crew/my", "My sign-ups"]];

export default function App() {
  const { user } = useAuth();
  const { data: site } = useSite();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { pathname } = useLocation();
  const links = user?.role === "skipper" ? SKIPPER_LINKS : user?.role === "crew" ? CREW_LINKS
    : user?.manages_boats ? [...LINKS, ...SKIPPER_LINKS] : LINKS;
  const cognito = site?.auth_mode === "cognito";
  const logout = async () => {
    await api("/auth/logout", { method: "POST" });
    // Cognito mode: signing out means forgetting the tokens the club website's sign-in page keeps in this tab
    if (cognito) clearTokens(window.sessionStorage, (await authSettings()).keys);
    await qc.invalidateQueries({ queryKey: ["me"] });
    nav("/");
  };
  return (
    <AppShell header={{ height: 62 }} padding="md" className="page-bg">
      <AppShell.Header className="site-header">
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="lg" wrap="nowrap">
            <Link to="/" className="site-brand">
              <Burgee height={36} />
              <span className="name">{site?.app_name ?? "Race Results"}</span>
            </Link>
            <Anchor component={Link} to="/crew" size="sm" fw={pathname === "/crew" ? 700 : 500} underline="hover">Crew board</Anchor>
            {user && !user.must_change_password && (
              <Group gap="md" visibleFrom="md" wrap="nowrap">
                {links.map(([to, label]) => (
                  <Anchor key={to} component={Link} to={to} size="sm" fw={pathname.startsWith(to) ? 700 : 500}
                    underline={pathname.startsWith(to) ? "always" : "hover"}>
                    {label}
                  </Anchor>
                ))}
              </Group>
            )}
          </Group>
          <Group gap="xs" wrap="nowrap">
            {user ? (
              <>
                <Menu>
                  <Menu.Target>
                    <Button size="compact-sm" variant="light" hiddenFrom="md">Menu</Button>
                  </Menu.Target>
                  <Menu.Dropdown>
                    {links.map(([to, label]) => (
                      <Menu.Item key={to} component={Link} to={to}>{label}</Menu.Item>
                    ))}
                    {!cognito && <Menu.Divider />}
                    {!cognito && <Menu.Item component={Link} to="/change-password">Change password</Menu.Item>}
                  </Menu.Dropdown>
                </Menu>
                <Text size="sm" visibleFrom="sm" c="dimmed">{user.display_name || user.username}</Text>
                {user.manages_boats && user.unseen_requests > 0 && (
                  <Badge color="red" variant="filled" component={Link} to="/skipper" title="New crew requests">{user.unseen_requests}</Badge>
                )}
                {!cognito && <Button component={Link} to="/change-password" size="compact-sm" variant="subtle" visibleFrom="sm">Change password</Button>}
                <Button size="compact-sm" variant="default" onClick={logout}>Log out</Button>
              </>
            ) : (
              <Button component={Link} to="/login" size="compact-sm" variant="light">Sign in</Button>
            )}
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <div className={pathname === "/" ? undefined : "page"}>
          <Routes>
            <Route path="/" element={<SeriesList />} />
            <Route path="/series/:id" element={<SeriesPage />} />
            <Route path="/races/:id" element={<RacePage />} />
            <Route path="/boats/:id" element={<BoatPage />} />
            <Route path="/login" element={<Login />} />
            <Route path="/change-password" element={<RequireSignedIn><ChangePassword /></RequireSignedIn>} />
            <Route path="/rc" element={<RequireEditor><RcHome /></RequireEditor>} />
            <Route path="/rc/races/:raceId" element={<RequireEditor><RcRace /></RequireEditor>} />
            <Route path="/manage/boats" element={<RequireEditor><Boats /></RequireEditor>} />
            <Route path="/manage/fleets" element={<RequireEditor><Fleets /></RequireEditor>} />
            <Route path="/manage/courses" element={<RequireEditor><Courses /></RequireEditor>} />
            <Route path="/manage/series" element={<RequireEditor><SeriesManage /></RequireEditor>} />
            <Route path="/crew" element={<CrewBoard />} />
            <Route path="/crew/join" element={<CrewJoin />} />
            <Route path="/crew/my" element={<RequireEditor role="crew"><MySignups /></RequireEditor>} />
            <Route path="/skipper" element={<RequireEditor role={["skipper", "rc"]}><SkipperHome /></RequireEditor>} />
            <Route path="/manage/crew" element={<RequireEditor><CrewAdmin /></RequireEditor>} />
            <Route path="*" element={<Text>Page not found.</Text>} />
          </Routes>
        </div>
        <div className="page"><SiteFooter /></div>
      </AppShell.Main>
    </AppShell>
  );
}
