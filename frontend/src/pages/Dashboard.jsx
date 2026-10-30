import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  ArrowDownToLine, ArrowRight, Bell, CalendarDays, Check, CircleUserRound,
  ClipboardList, Download, FileText, LayoutDashboard, LogOut, Plus, Search,
  Send, Settings, ShieldCheck, Ticket, Trash2, Upload, Users, X,
} from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import QRCodeScanner from "../components/QRCodeScanner";
import { EventCard, Loading, Notice, PageTitle, StatusPill } from "../components/shared";
import { useAuth } from "../context/AuthContext";
import api, { downloadFile, errorMessage } from "../services/api";

const chartColors = ["#6856dd", "#f0a184", "#59a28e", "#8d83e8", "#e7bb55", "#6699d1"];

function useData(path, fallback = []) {
  const [data, setData] = useState(fallback);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data: response } = await api.get(path);
      setData(response);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => { load(); }, [load]);
  return { data, setData, error, setError, loading, load };
}

function MetricCards({ entries }) {
  return <div className="stats-grid">{entries.map(([key, value]) => <div className="metric" key={key}>
    <span>{key.replaceAll("_", " ")}</span><strong>{typeof value === "number" && key.includes("revenue") ? `₹${value.toLocaleString("en-IN")}` : value ?? "—"}</strong>
  </div>)}</div>;
}

function Sidebar({ role, tab, setTab }) {
  const groups = role === "admin"
    ? [["overview", "Overview", LayoutDashboard], ["events", "Events", CalendarDays], ["organizers", "Organizers", Users], ["users", "Users", CircleUserRound], ["registrations", "Registrations", ClipboardList], ["categories", "Categories", Settings], ["reports", "Reports", FileText], ["activity", "Activity log", ShieldCheck]]
    : role === "organizer"
      ? [["overview", "Overview", LayoutDashboard], ["events", "My events", CalendarDays], ["participants", "Participants", Users], ["scanner", "Check-in scanner", Ticket], ["analytics", "Analytics", FileText], ["profile", "Organization profile", Settings], ["notifications", "Notifications", Bell]]
      : [["overview", "Overview", LayoutDashboard], ["registrations", "My registrations", Ticket], ["profile", "My profile", CircleUserRound], ["notifications", "Notifications", Bell]];
  return <aside className="dashboard-sidebar">
    <div className="sidebar-label">{role === "admin" ? "ADMIN" : role === "organizer" ? "ORGANIZER" : "PARTICIPANT"}</div>
    {groups.map(([id, label, Icon]) => <button key={id} className={`sidebar-link${tab === id ? " active" : ""}`} onClick={() => setTab(id)}><Icon size={17}/>{label}</button>)}
  </aside>;
}

function DashboardLayout({ role, tab, setTab, children }) {
  return <div className="dashboard-layout"><Sidebar role={role} tab={tab} setTab={setTab}/><div className="dashboard-content">{children}</div></div>;
}

export default function Dashboard() {
  const { user, setUser } = useAuth();
  const [params, setParams] = useSearchParams();
  const availableTabs = useMemo(() => ({
    admin: ["overview", "events", "organizers", "users", "registrations", "categories", "reports", "activity"],
    organizer: ["overview", "events", "participants", "scanner", "analytics", "profile", "notifications"],
    user: ["overview", "registrations", "profile", "notifications"],
  })[user.role], [user.role]);
  const initialTab = params.get("tab");
  const [tab, updateTab] = useState(availableTabs.includes(initialTab) ? initialTab : "overview");
  useEffect(() => {
    if (initialTab && availableTabs.includes(initialTab)) updateTab(initialTab);
  }, [initialTab, availableTabs]);
  function setTab(value) {
    updateTab(value);
    const next = new URLSearchParams(params);
    if (value === "overview") next.delete("tab");
    else next.set("tab", value);
    setParams(next, { replace: true });
  }
  return <main className="dashboard-page">
    <header className="dashboard-header">
      <div><span className="eyebrow purple">{user.role === "admin" ? "ADMINISTRATION" : user.role === "organizer" ? "ORGANIZER SPACE" : "YOUR GATHERLY"}</span><h1>Welcome, {user.full_name}</h1></div>
      <Link to="/events" className="button button-outline">Explore events <ArrowRight size={16}/></Link>
    </header>
    <DashboardLayout role={user.role} tab={tab} setTab={setTab}>
      {user.role === "admin" && <AdminPanel tab={tab} setTab={setTab}/>}
      {user.role === "organizer" && <OrganizerPanel tab={tab} user={user} setUser={setUser}/>}
      {user.role === "user" && <ParticipantPanel tab={tab} user={user} setUser={setUser}/>}
    </DashboardLayout>
  </main>;
}

function AdminPanel({ tab, setTab }) {
  if (tab === "overview") return <AdminOverview setTab={setTab}/>;
  if (tab === "events") return <AdminEventManagement/>;
  if (tab === "organizers") return <OrganizerApplications/>;
  if (tab === "users") return <AdminUserManagement/>;
  if (tab === "registrations") return <AdminRegistrations/>;
  if (tab === "categories") return <CategoryManagement/>;
  if (tab === "reports") return <Reports/>;
  return <ActivityLog/>;
}

function AdminOverview({ setTab }) {
  const { data, error, loading } = useData("/admin/dashboard", {});
  if (loading) return <Loading/>;
  const metrics = [
    ["total_users", data.total_users],
    ["total_organizers", data.total_organizers],
    ["total_events", data.total_events],
    ["pending_events", data.pending_events],
    ["total_registrations", data.total_registrations],
    ["total_revenue", data.total_revenue],
  ];
  return <>
    <PageTitle eyebrow="SYSTEM OVERVIEW" title="Platform dashboard" description="Live activity and platform statistics." action={<button className="button button-primary small" onClick={() => setTab("events")}>Review pending <ArrowRight size={15}/></button>}/>
    <Notice error={error}/>
    <MetricCards entries={metrics}/>
    <div className="charts-grid">
      <ChartCard title="Monthly registrations"><ResponsiveContainer width="100%" height={240}><LineChart data={data.monthly_registrations}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="month"/><YAxis allowDecimals={false}/><Tooltip/><Line type="monotone" dataKey="count" stroke="#6856dd" strokeWidth={3} dot={false}/></LineChart></ResponsiveContainer></ChartCard>
      <ChartCard title="Event categories"><ResponsiveContainer width="100%" height={240}><PieChart><Pie data={data.category_distribution} dataKey="count" nameKey="category" innerRadius={55} outerRadius={85} paddingAngle={3}>{data.category_distribution.map((entry, index) => <Cell key={entry.category} fill={chartColors[index % chartColors.length]}/>)}</Pie><Tooltip/></PieChart></ResponsiveContainer></ChartCard>
      <ChartCard title="Monthly events"><ResponsiveContainer width="100%" height={240}><BarChart data={data.monthly_events}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="month"/><YAxis allowDecimals={false}/><Tooltip/><Bar dataKey="count" fill="#6856dd" radius={[5, 5, 0, 0]}/></BarChart></ResponsiveContainer></ChartCard>
      <ChartCard title="Recent activity"><ActivityRows items={data.recent_activity || []}/></ChartCard>
    </div>
  </>;
}

function ChartCard({ title, children }) {
  return <section className="chart-card"><h3>{title}</h3>{children}</section>;
}

function ActivityRows({ items }) {
  if (!items.length) return <div className="empty-state compact">No activity recorded yet.</div>;
  return <div className="activity-list">{items.slice(0, 8).map((item) => <div className="activity-item" key={item.id}><span className="activity-dot"/><div><strong>{item.description}</strong><small>{new Date(item.created_at).toLocaleString()}</small></div></div>)}</div>;
}

function AdminEventManagement() {
  const [filter, setFilter] = useState("pending");
  const [search, setSearch] = useState("");
  const { data, error, loading, load } = useData(`/admin/events?approval_status=${filter}&search=${encodeURIComponent(search)}`, {});
  async function decide(id, action) {
    let payload;
    if (action === "reject") {
      const reason = window.prompt("Enter the reason for rejecting this event:");
      if (!reason?.trim()) return;
      payload = { reason };
    }
    try {
      await api.put(`/admin/events/${id}/${action}`, payload);
      await load();
    } catch (requestError) {
      window.alert(errorMessage(requestError));
    }
  }
  async function cancel(event) {
    const reason = window.prompt("Enter a cancellation reason:");
    if (!reason?.trim()) return;
    try {
      await api.post(`/events/${event.id}/cancel`, { reason });
      await load();
    } catch (requestError) {
      window.alert(errorMessage(requestError));
    }
  }
  return <>
    <PageTitle eyebrow="EVENT MODERATION" title="Manage events" description="Review submissions and oversee every platform event."/>
    <div className="table-toolbar"><label>Approval status<select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">All statuses</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="draft">Drafts</option></select></label><label>Search<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Event or city"/></label><button className="button button-quiet" onClick={load}>Refresh</button></div>
    <Notice error={error}/>{loading ? <Loading/> : <div className="table-wrap"><table><thead><tr><th>Event</th><th>Organizer</th><th>Date</th><th>Status</th><th>Capacity</th><th>Actions</th></tr></thead><tbody>
      {data.items?.map((event) => <tr key={event.id}><td><strong>{event.title}</strong><small>{event.category?.name}</small>{event.rejection_reason && <small className="text-error">{event.rejection_reason}</small>}</td><td>{event.organizer}</td><td>{new Date(event.start_at).toLocaleDateString()}</td><td><StatusPill value={event.approval_status}/></td><td>{event.available_seats}/{event.capacity}</td><td className="table-actions">{event.approval_status === "pending" && <><button className="icon-button approve" title="Approve" onClick={() => decide(event.id, "approve")}><Check size={16}/></button><button className="icon-button reject" title="Reject" onClick={() => decide(event.id, "reject")}><X size={16}/></button></>}{event.event_status === "active" && event.approval_status === "approved" && <button className="button button-quiet small" onClick={() => cancel(event)}>Cancel</button>}</td></tr>)}
    </tbody></table>{!data.items?.length && <div className="empty-state">No events match this view.</div>}</div>}
  </>;
}

function OrganizerApplications() {
  const [filter, setFilter] = useState("pending");
  const { data, error, loading, load } = useData(`/admin/organizers?approval_status=${filter}`, {});
  async function decision(organizer, action) {
    let payload;
    if (action === "reject") {
      const reason = window.prompt("Enter a reason for rejecting this application:");
      if (!reason?.trim()) return;
      payload = { reason };
    }
    try {
      await api.put(`/admin/organizers/${organizer.id}/${action}`, payload);
      await load();
    } catch (requestError) {
      window.alert(errorMessage(requestError));
    }
  }
  async function toggle(organizer) {
    try {
      await api.put(`/admin/organizers/${organizer.id}/status`, { active: organizer.account_status !== "active" });
      await load();
    } catch (requestError) {
      window.alert(errorMessage(requestError));
    }
  }
  async function getFile(id, kind) {
    try {
      await downloadFile(`/admin/organizers/${id}/files/${kind}`, `${kind}-${id}`);
    } catch (requestError) {
      window.alert(errorMessage(requestError));
    }
  }
  return <>
    <PageTitle eyebrow="ORGANIZER REVIEW" title="Organizer applications" description="Review applications, verify documents, and manage organizer access."/>
    <div className="table-toolbar"><label>Application status<select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">All</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select></label></div>
    <Notice error={error}/>{loading ? <Loading/> : <div className="table-wrap"><table><thead><tr><th>Organizer</th><th>Organization</th><th>Contact</th><th>Documents</th><th>Status</th><th>Actions</th></tr></thead><tbody>
      {data.items?.map((item) => <tr key={item.id}><td><strong>{item.full_name}</strong><small>{item.email}</small>{item.rejection_reason && <small className="text-error">{item.rejection_reason}</small>}</td><td>{item.organization_name}<small>{item.organization_address}</small></td><td>{item.phone}</td><td className="table-actions">{item.organization_logo && <button className="button button-quiet small" onClick={() => getFile(item.id, "logo")}>Logo</button>}{item.supporting_document && <button className="button button-quiet small" onClick={() => getFile(item.id, "document")}>Document</button>}</td><td><StatusPill value={item.approval_status}/><small>{item.account_status}</small></td><td className="table-actions">{item.approval_status === "pending" && <><button className="button button-primary small" onClick={() => decision(item, "approve")}>Approve</button><button className="button button-quiet small" onClick={() => decision(item, "reject")}>Reject</button></>}{item.approval_status === "approved" && <button className="button button-quiet small" onClick={() => toggle(item)}>{item.account_status === "active" ? "Suspend" : "Activate"}</button>}</td></tr>)}
    </tbody></table>{!data.items?.length && <div className="empty-state">No organizer applications in this status.</div>}</div>}</>;
}

function AdminUserManagement() {
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const { data, error, loading, load } = useData(`/admin/users?role=${role}&search=${encodeURIComponent(search)}`, {});
  async function toggle(user) {
    try {
      await api.put(`/admin/users/${user.id}/status`, { account_status: user.account_status === "active" ? "inactive" : "active" });
      await load();
    } catch (requestError) {
      window.alert(errorMessage(requestError));
    }
  }
  return <>
    <PageTitle eyebrow="ACCOUNT MANAGEMENT" title="Users and organizers" description="Find an account, edit its status, or review its profile."/>
    <div className="table-toolbar"><label>Role<select value={role} onChange={(event) => setRole(event.target.value)}><option value="">All roles</option><option value="user">Participants</option><option value="organizer">Organizers</option></select></label><label>Search<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or email"/></label><button className="button button-quiet" onClick={load}>Refresh</button></div>
    <Notice error={error}/>{loading ? <Loading/> : <div className="table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead><tbody>{data.items?.map((item) => <tr key={item.id}><td>{item.full_name}<small>{item.organization_name || item.college_name}</small></td><td>{item.email}</td><td>{item.phone || "—"}</td><td>{item.role}</td><td><StatusPill value={item.account_status}/></td><td>{item.role !== "admin" && <button className="button button-quiet small" onClick={() => toggle(item)}>{item.account_status === "active" ? "Deactivate" : "Activate"}</button>}</td></tr>)}</tbody></table>{!data.items?.length && <div className="empty-state">No accounts found.</div>}</div>}</>;
}

function AdminRegistrations() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const { data, error, loading, load } = useData(`/admin/registrations?status=${status}&search=${encodeURIComponent(search)}`, {});
  async function cancel(item) {
    if (!window.confirm(`Cancel ${item.registration_number}?`)) return;
    try {
      await api.put(`/admin/registrations/${item.id}/cancel`);
      await load();
    } catch (requestError) {
      window.alert(errorMessage(requestError));
    }
  }
  return <>
    <PageTitle eyebrow="REGISTRATION OVERSIGHT" title="Registrations" description="Search tickets, payments, and event attendance."/>
    <div className="table-toolbar"><label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option value="confirmed">Confirmed</option><option value="pending_payment">Payment pending</option><option value="cancelled">Cancelled</option><option value="expired">Expired</option></select></label><label>Search<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Participant or event"/></label><button className="button button-quiet" onClick={load}>Refresh</button></div>
    <Notice error={error}/>{loading ? <Loading/> : <div className="table-wrap"><table><thead><tr><th>Participant</th><th>Event</th><th>Registration</th><th>Payment</th><th>Attendance</th><th>Actions</th></tr></thead><tbody>{data.items?.map((item) => <tr key={item.id}><td>{item.participant}<small>{item.email}</small></td><td>{item.event}</td><td>{item.registration_number}<small><StatusPill value={item.registration_status}/></small></td><td><StatusPill value={item.payment_status}/></td><td><StatusPill value={item.attendance_status}/></td><td>{item.registration_status === "confirmed" && <button className="button button-quiet small" onClick={() => cancel(item)}>Cancel</button>}</td></tr>)}</tbody></table>{!data.items?.length && <div className="empty-state">No registrations found.</div>}</div>}</>;
}

function CategoryManagement() {
  const { data, error, loading, load } = useData("/admin/categories", {});
  const [submitError, setSubmitError] = useState("");
  async function add(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setSubmitError("");
    const form = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await api.post("/admin/categories", form);
      formElement.reset();
      await load();
    } catch (requestError) {
      setSubmitError(errorMessage(requestError));
    }
  }
  async function toggle(category) {
    try {
      await api.put(`/admin/categories/${category.id}`, { active: !category.active });
      await load();
    } catch (requestError) {
      setSubmitError(errorMessage(requestError));
    }
  }
  return <>
    <PageTitle eyebrow="APPLICATION SETTINGS" title="Event categories" description="Manage the categories organizers can choose for new events."/>
    <form className="inline-form" onSubmit={add}><label>Category name<input name="name" required maxLength="80"/></label><label>Description<input name="description" maxLength="255"/></label><button className="button button-primary"><Plus size={16}/> Add category</button></form>
    <Notice error={error || submitError}/>
    {loading ? <Loading/> : <div className="table-wrap"><table><thead><tr><th>Category</th><th>Description</th><th>Status</th><th>Action</th></tr></thead><tbody>{data.items?.map((item) => <tr key={item.id}><td>{item.name}</td><td>{item.description || "—"}</td><td><StatusPill value={item.active ? "active" : "inactive"}/></td><td><button className="button button-quiet small" onClick={() => toggle(item)}>{item.active ? "Deactivate" : "Activate"}</button></td></tr>)}</tbody></table></div>}
  </>;
}

function Reports() {
  const [error, setError] = useState("");
  async function getReport(path, filename) {
    setError("");
    try {
      await downloadFile(path, filename);
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  return <>
    <PageTitle eyebrow="DATA AND INSIGHTS" title="Reports" description="Download live operational and financial reports."/>
    <Notice error={error}/>
    <div className="report-grid">{[
      ["Event registrations", "events"],
      ["Participant registrations", "registrations"],
      ["Payments and revenue", "revenue"],
      ["Attendance", "attendance"],
      ["Category distribution", "categories"],
    ].map(([label, type]) => <article className="report-card" key={type}><FileText size={22}/><h3>{label}</h3><p>Export current platform records as a CSV spreadsheet.</p><button className="button button-outline" onClick={() => getReport(`/admin/reports?type=${type}`, `gatherly-${type}.csv`)}>Download CSV <Download size={15}/></button></article>)}
      <article className="report-card"><FileText size={22}/><h3>Platform summary</h3><p>Download key totals and category distribution as a PDF report.</p><button className="button button-outline" onClick={() => getReport("/admin/reports.pdf", "gatherly-report.pdf")}>Download PDF <Download size={15}/></button></article>
    </div>
  </>;
}

function ActivityLog() {
  const { data, error, loading } = useData("/admin/activity", {});
  return <>
    <PageTitle eyebrow="AUDIT TRAIL" title="System activity" description="Recent administrator and account actions."/>
    <Notice error={error}/>{loading ? <Loading/> : <div className="table-wrap"><table><thead><tr><th>Action</th><th>Details</th><th>Role</th><th>Time</th></tr></thead><tbody>{data.items?.map((item) => <tr key={item.id}><td><StatusPill value={item.action}/></td><td>{item.description}</td><td>{item.actor_role}</td><td>{new Date(item.created_at).toLocaleString()}</td></tr>)}</tbody></table>{!data.items?.length && <div className="empty-state">No activity has been recorded.</div>}</div>}
  </>;
}

function ParticipantPanel({ tab, user, setUser }) {
  if (tab === "profile") return <ProfilePanel user={user} setUser={setUser}/>;
  if (tab === "notifications") return <NotificationsPanel/>;
  if (tab === "registrations") return <ParticipantRegistrations/>;
  return <ParticipantOverview user={user} setTab={() => {}}/>;
}

function ParticipantOverview({ user }) {
  const { data, error, loading } = useData("/registrations/my", {});
  const registrations = data.items || [];
  if (loading) return <Loading/>;
  const now = new Date();
  const upcoming = registrations.filter((item) => item.status === "confirmed" && new Date(item.event.end_at) >= now);
  const completed = registrations.filter((item) => new Date(item.event.end_at) < now);
  return <>
    <PageTitle eyebrow="YOUR EVENTS" title={`Hello, ${user.full_name.split(" ")[0]}`} description="Your tickets and the next things to look forward to." action={<Link className="button button-primary small" to="/events">Find an event <ArrowRight size={15}/></Link>}/>
    <Notice error={error}/>
    <MetricCards entries={[["registered_events", registrations.length], ["upcoming_events", upcoming.length], ["completed_events", completed.length], ["cancelled_registrations", registrations.filter((item) => item.status === "cancelled").length]]}/>
    <h2 className="dashboard-subtitle">Coming up</h2>
    {upcoming.slice(0, 3).map((item) => <RegistrationRow key={item.id} registration={item}/>)}
    {!upcoming.length && <div className="empty-state">No upcoming events yet. <Link to="/events">Find one to join.</Link></div>}
  </>;
}

function ParticipantRegistrations() {
  const { data, error, loading, load } = useData("/registrations/my", {});
  async function cancel(item) {
    if (!window.confirm(`Cancel your registration for ${item.event.title}?`)) return;
    try {
      await api.delete(`/registrations/${item.id}`);
      await load();
    } catch (requestError) {
      window.alert(errorMessage(requestError));
    }
  }
  if (loading) return <Loading/>;
  return <>
    <PageTitle eyebrow="YOUR TICKETS" title="My registrations" description="Manage your event bookings, tickets, and feedback." action={<Link className="button button-primary small" to="/events">Discover events <ArrowRight size={15}/></Link>}/>
    <Notice error={error}/>
    {(data.items || []).map((item) => <RegistrationRow registration={item} key={item.id} onCancel={() => cancel(item)}/>)}
    {!data.items?.length && <div className="empty-state">No registrations yet. <Link to="/events">Explore upcoming events.</Link></div>}
  </>;
}

function RegistrationRow({ registration, onCancel }) {
  const [showTicket, setShowTicket] = useState(false);
  const isUpcoming = new Date(registration.event.end_at) >= new Date();
  return <article className="registration-card">
    <div className="registration-main">
      <div className="registration-art"><CalendarDays size={23}/></div>
      <div className="registration-details"><Link to={`/events/${registration.event.id}`}><h3>{registration.event.title}</h3></Link><p>{new Date(registration.event.start_at).toLocaleString()} · {registration.event.venue || "Online"}</p><small>Registration {registration.registration_number} · {new Date(registration.created_at).toLocaleDateString()}</small></div>
      <div className="registration-status"><StatusPill value={registration.status}/><StatusPill value={registration.payment_status}/></div>
    </div>
    <div className="registration-actions">
      {registration.status === "confirmed" && registration.ticket && <button className="button button-primary small" onClick={() => setShowTicket(!showTicket)}><Ticket size={15}/>{showTicket ? "Hide ticket" : "View ticket"}</button>}
      {registration.status === "confirmed" && isUpcoming && <button className="button button-quiet small" onClick={onCancel}>Cancel registration</button>}
      {!isUpcoming && registration.status === "confirmed" && <FeedbackForm eventId={registration.event.id}/>}
    </div>
    {showTicket && <TicketDetails registration={registration}/>}
  </article>;
}

function TicketDetails({ registration }) {
  const [qr, setQr] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let url;
    api.get(`/tickets/${registration.id}/qr`, { responseType: "blob" }).then(({ data }) => {
      url = URL.createObjectURL(data);
      setQr(url);
    }).catch((requestError) => setError(errorMessage(requestError)));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [registration.id]);
  async function download() {
    try {
      await downloadFile(`/tickets/${registration.id}/download`, `gatherly-${registration.registration_number}.pdf`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  return <div className="ticket-detail">
    <div>{qr ? <img src={qr} alt="Ticket QR code"/> : <div className="loading">Loading QR…</div>}</div>
    <div><span className="eyebrow">YOUR DIGITAL TICKET</span><h3>{registration.event.title}</h3><p>{registration.event.organizer} · {new Date(registration.event.start_at).toLocaleString()}</p><strong>{registration.ticket.ticket_number}</strong><button className="button button-outline small" onClick={download}><ArrowDownToLine size={15}/> Download PDF</button><Notice error={error}/></div>
  </div>;
}

function FeedbackForm({ eventId }) {
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setError("");
    const values = Object.fromEntries(new FormData(formElement));
    try {
      await api.post("/feedback", { ...values, event_id: eventId, rating: Number(values.rating) });
      setSent(true);
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  if (sent) return <span className="feedback-sent"><Check size={15}/> Feedback sent</span>;
  return <details className="feedback-details"><summary>Leave feedback</summary><form onSubmit={submit} className="feedback-form">
    <label>Rating<select name="rating" required defaultValue="5"><option value="5">5 — Excellent</option><option value="4">4 — Great</option><option value="3">3 — Good</option><option value="2">2 — Fair</option><option value="1">1 — Needs improvement</option></select></label>
    <label>Comments<textarea name="comments" maxLength="5000" rows="2"/></label><label>Suggestions<textarea name="suggestions" maxLength="5000" rows="2"/></label>
    <button className="button button-primary small">Submit feedback</button><Notice error={error}/>
  </form></details>;
}

function OrganizerPanel({ tab, user, setUser }) {
  if (tab === "profile") return <ProfilePanel user={user} setUser={setUser}/>;
  if (tab === "notifications") return <NotificationsPanel/>;
  if (tab === "events") return <OrganizerEvents/>;
  if (tab === "participants") return <ParticipantsPanel/>;
  if (tab === "scanner") return <AttendanceScanner/>;
  if (tab === "analytics") return <OrganizerAnalytics/>;
  return <OrganizerOverview user={user}/>;
}

function OrganizerOverview({ user }) {
  const { data: stats, error, loading } = useData("/events/dashboard", {});
  const { data: eventsData } = useData("/events/mine", {});
  const { data: analytics } = useData("/events/analytics", {});
  if (loading) return <Loading/>;
  return <>
    <PageTitle eyebrow="YOUR COMMUNITY" title={user.organization_name || "Organizer dashboard"} description={user.approval_status === "approved" ? "Track your events and the community around them." : `Your organizer application is ${user.approval_status}.`} action={user.approval_status === "approved" ? <button className="button button-primary small" onClick={() => document.getElementById("create-event")?.scrollIntoView({ behavior: "smooth" })}><Plus size={15}/> Create event</button> : null}/>
    <Notice error={error}/>
    {user.approval_status === "approved" ? <>
      <MetricCards entries={Object.entries(stats)}/>
      <ChartCard title="Registrations by month"><ResponsiveContainer width="100%" height={240}><LineChart data={analytics.monthly_registrations || []}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="month"/><YAxis allowDecimals={false}/><Tooltip/><Line dataKey="count" type="monotone" stroke="#6856dd" strokeWidth={3}/></LineChart></ResponsiveContainer></ChartCard>
      <h2 className="dashboard-subtitle">Your events</h2><div className="event-grid">{(eventsData.items || []).slice(0, 3).map((event) => <EventCard key={event.id} event={event}/>)}</div>
      {!eventsData.items?.length && <div className="empty-state">Your first event is one good idea away. <button className="text-link" onClick={() => document.getElementById("create-event")?.scrollIntoView({ behavior: "smooth" })}>Create an event</button></div>}
      <CreateEventForm id="create-event"/>
    </> : <div className="empty-state">Your account must be approved by an administrator before you can create public events.</div>}
  </>;
}

function CreateEventForm({ id, onCreated }) {
  const { data } = useData("/events/categories", {});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  async function submit(formElement, saveAs) {
    setError("");
    setMessage("");
    setSaving(true);
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const form = {
      ...values,
      category_id: Number(values.category_id),
      capacity: Number(values.capacity),
      fee: Number(values.fee),
      start_at: new Date(values.start_at).toISOString(),
      end_at: new Date(values.end_at).toISOString(),
      registration_start: values.registration_start ? new Date(values.registration_start).toISOString() : new Date().toISOString(),
      registration_deadline: new Date(values.registration_deadline).toISOString(),
      save_as: saveAs,
    };
    try {
      const { data: response } = await api.post("/events", form);
      setMessage(saveAs === "draft" ? "Draft saved." : "Event submitted for admin approval.");
      formElement.reset();
      onCreated?.(response.event);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSaving(false);
    }
  }
  return <section className="form-panel" id={id}>
    <h2>Create an event</h2>
    <form className="form-grid" onSubmit={(event) => { event.preventDefault(); submit(event.currentTarget, "submit"); }}>
      <label>Event title<input name="title" maxLength="180" required/></label>
      <label>Category<select name="category_id" required><option value="">Choose category</option>{(data.items || []).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      <label>Event format<select name="event_type"><option value="offline">In person</option><option value="online">Online</option><option value="hybrid">Hybrid</option></select></label>
      <label>Capacity<input name="capacity" type="number" min="1" required/></label>
      <label>Starts<input name="start_at" type="datetime-local" required/></label>
      <label>Ends<input name="end_at" type="datetime-local" required/></label>
      <label>Registration opens<input name="registration_start" type="datetime-local"/></label>
      <label>Registration closes<input name="registration_deadline" type="datetime-local" required/></label>
      <label>Registration fee (INR)<input name="fee" type="number" min="0" step="0.01" defaultValue="0" required/></label>
      <label>Venue<input name="venue" maxLength="180"/></label>
      <label className="span-two">Full address<input name="address" maxLength="255"/></label>
      <label>City<input name="city" maxLength="100"/></label><label>State<input name="state" maxLength="100"/></label>
      <label>Postal code<input name="postal_code" maxLength="20"/></label><label>Online meeting link<input name="online_meeting_link" type="url"/></label>
      <label className="span-two">Event description<textarea name="description" rows="4" maxLength="12000" required/></label>
      <label>Eligibility criteria<textarea name="eligibility" rows="2"/></label><label>Age restrictions<input name="age_restriction"/></label>
      <label>Department restrictions<input name="department_restriction"/></label><label>Contact person<input name="contact_person"/></label>
      <label>Contact email<input name="contact_email" type="email"/></label><label>Contact phone<input name="contact_phone" type="tel"/></label>
      <label>Event website<input name="website" type="url"/></label><label>Required materials<textarea name="required_materials" rows="2"/></label>
      <label className="span-two">Event rules<textarea name="event_rules" rows="3"/></label>
      <div className="button-row"><button type="button" className="button button-quiet" disabled={saving} onClick={(event) => submit(event.currentTarget.form, "draft")}>Save draft</button><button className="button button-primary" disabled={saving}>{saving ? "Saving…" : "Submit for approval"} <ArrowRight size={16}/></button></div>
      <Notice error={error} message={message}/>
    </form>
  </section>;
}

function OrganizerEvents() {
  const { data, error, loading, load } = useData("/events/mine", {});
  return <>
    <PageTitle eyebrow="EVENT OPERATIONS" title="My events" description="Edit drafts, resubmit event changes, or manage event status."/>
    <Notice error={error}/>{loading ? <Loading/> : <div className="managed-events">{(data.items || []).map((event) => <ManagedEvent event={event} key={event.id} onChange={load}/>)}</div>}
    {!data.items?.length && !loading && <div className="empty-state">No events created yet. <Link to="/dashboard">Create your first event.</Link></div>}
  </>;
}

function ManagedEvent({ event, onChange }) {
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function cancel() {
    const reason = window.prompt("Enter a reason for cancelling this event:");
    if (!reason?.trim()) return;
    try {
      await api.post(`/events/${event.id}/cancel`, { reason });
      setMessage("Event cancelled and participants notified.");
      onChange();
    } catch (requestError) { setError(errorMessage(requestError)); }
  }
  async function remove() {
    if (!window.confirm(`Delete the draft "${event.title}"?`)) return;
    try { await api.delete(`/events/${event.id}`); onChange(); }
    catch (requestError) { setError(errorMessage(requestError)); }
  }
  async function resubmit() {
    try { await api.put(`/events/${event.id}/submit`); onChange(); }
    catch (requestError) { setError(errorMessage(requestError)); }
  }
  return <article className="managed-event">
    <div className="managed-event-head"><div><h3>{event.title}</h3><span>{event.category?.name} · {new Date(event.start_at).toLocaleString()}</span></div><StatusPill value={event.approval_status}/></div>
    {event.rejection_reason && <Notice error={`Reviewer notes: ${event.rejection_reason}`}/>}
    <div className="managed-event-actions">
      <Link className="button button-quiet small" to={`/events/${event.id}`}>View details</Link>
      {(event.approval_status === "draft" || event.approval_status === "rejected") && <><button className="button button-quiet small" onClick={resubmit}>Submit for approval</button>{event.approval_status !== "rejected" && <button className="button button-quiet small danger-action" onClick={remove}>Delete draft</button>}</>}
      {event.approval_status === "approved" && event.event_status === "active" && <><Link className="button button-quiet small" to={`/dashboard?tab=participants&event=${event.id}`}>Participants ({event.capacity - event.available_seats})</Link><button className="button button-quiet small danger-action" onClick={cancel}>Cancel event</button></>}
    </div>
    <Notice error={error} message={message}/>
    {event.event_status !== "cancelled" && <details className="edit-event-details"><summary>Edit event details</summary><EditEventForm event={event} onSaved={onChange}/></details>}
    {event.approval_status === "approved" && event.event_status === "active" && <details className="edit-event-details"><summary>Send participant announcement</summary><AnnouncementForm event={event}/></details>}
  </article>;
}

function EditEventForm({ event, onSaved }) {
  const { data } = useData("/events/categories", {});
  const [error, setError] = useState("");
  function localDate(value) {
    const date = new Date(value);
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 16);
  }

  async function submit(formEvent) {
    formEvent.preventDefault();
    setError("");
    const values = Object.fromEntries(new FormData(formEvent.currentTarget));
    const payload = {
      ...values,
      category_id: Number(values.category_id),
      capacity: Number(values.capacity),
      fee: Number(values.fee),
      start_at: new Date(values.start_at).toISOString(),
      end_at: new Date(values.end_at).toISOString(),
      registration_start: new Date(values.registration_start).toISOString(),
      registration_deadline: new Date(values.registration_deadline).toISOString(),
    };
    try {
      await api.put(`/events/${event.id}`, payload);
      onSaved();
    } catch (requestError) { setError(errorMessage(requestError)); }
  }
  return <form className="form-grid" onSubmit={submit}>
    <label>Title<input name="title" defaultValue={event.title} required/></label>
    <label>Category<select name="category_id" defaultValue={event.category?.id}>{(data.items || []).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
    <label>Starts<input type="datetime-local" name="start_at" defaultValue={localDate(event.start_at)} required/></label>
    <label>Ends<input type="datetime-local" name="end_at" defaultValue={localDate(event.end_at)} required/></label>
    <label>Registration opens<input type="datetime-local" name="registration_start" defaultValue={localDate(event.registration_start)} required/></label>
    <label>Registration closes<input type="datetime-local" name="registration_deadline" defaultValue={localDate(event.registration_deadline)} required/></label>
    <label>Capacity<input type="number" name="capacity" min="1" defaultValue={event.capacity} required/></label>
    <label>Fee<input type="number" name="fee" min="0" step="0.01" defaultValue={event.fee} required/></label>
    <label>Venue<input name="venue" defaultValue={event.venue}/></label>
    <label>City<input name="city" defaultValue={event.city || ""}/></label>
    <label className="span-two">Description<textarea name="description" rows="3" defaultValue={event.description}/></label>
    <button className="button button-primary">Save changes and submit for approval</button><Notice error={error}/>
  </form>;
}

function AnnouncementForm({ event }) {
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function submit(formEvent) {
    formEvent.preventDefault();
    const formElement = formEvent.currentTarget;
    setError("");
    setMessage("");
    const values = Object.fromEntries(new FormData(formElement));
    try {
      const { data } = await api.post(`/events/${event.id}/announcements`, values);
      setMessage(data.message);
      formElement.reset();
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  return <form className="announcement-form" onSubmit={submit}><label>Title<input name="title" maxLength="160" required/></label><label>Message<textarea name="message" rows="3" required/></label><button className="button button-primary small"><Send size={15}/> Send to participants</button><Notice error={error} message={message}/></form>;
}

function ParticipantsPanel() {
  const [params] = useSearchParams();
  const [events, setEvents] = useState([]);
  const [eventId, setEventId] = useState(params.get("event") || "");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => { api.get("/events/mine").then(({ data }) => setEvents(data.items.filter((event) => event.approval_status === "approved"))).catch((requestError) => setError(errorMessage(requestError))); }, []);
  const load = useCallback(async () => {
    if (!eventId) return setItems([]);
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get(`/events/${eventId}/participants`, { params: { search, status } });
      setItems(data.items);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [eventId, search, status]);
  useEffect(() => { load(); }, [load]);
  return <>
    <PageTitle eyebrow="ATTENDEE MANAGEMENT" title="Participants" description="Search registrations, monitor check-in, and export your guest list."/>
    <div className="table-toolbar"><label>Event<select value={eventId} onChange={(event) => setEventId(event.target.value)}><option value="">Choose an event</option>{events.map((event) => <option value={event.id} key={event.id}>{event.title}</option>)}</select></label><label>Search<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or email"/></label><label>Registration<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All</option><option value="confirmed">Confirmed</option><option value="cancelled">Cancelled</option><option value="pending_payment">Payment pending</option></select></label>{eventId && <button className="button button-quiet" onClick={() => downloadFile(`/events/${eventId}/participants.csv`, `event-${eventId}-participants.csv`).catch((e) => setError(errorMessage(e)))}><Download size={15}/> Export CSV</button>}</div>
    <Notice error={error}/>{loading ? <Loading/> : <div className="table-wrap"><table><thead><tr><th>Name</th><th>Contact</th><th>Registration ID</th><th>Payment</th><th>Attendance</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{item.full_name}</td><td>{item.email}<small>{item.phone || "—"}</small></td><td>{item.registration_number}</td><td><StatusPill value={item.payment_status}/></td><td><StatusPill value={item.attendance_status}/></td></tr>)}</tbody></table>{eventId && !items.length && <div className="empty-state">No participants match.</div>}</div>}
  </>;
}

function AttendanceScanner() {
  const [events, setEvents] = useState([]);
  const [eventId, setEventId] = useState("");
  const [token, setToken] = useState("");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const onScan = useCallback((value) => {
    setToken(value);
    verify(value);
  }, [eventId]);
  useEffect(() => { api.get("/events/mine").then(({ data }) => setEvents(data.items.filter((event) => event.approval_status === "approved" && event.event_status === "active"))).catch((requestError) => setError(errorMessage(requestError))); }, []);
  async function verify(value = token) {
    setError("");
    setResult("");
    if (!eventId || !value.trim()) {
      setError("Choose an event and scan or enter a ticket QR token.");
      return;
    }
    try {
      const { data } = await api.post("/attendance/verify", { event_id: Number(eventId), qr_token: value.trim() });
      setResult(`${data.participant} checked in for ${data.event}.`);
      setToken("");
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  return <>
    <PageTitle eyebrow="EVENT CHECK-IN" title="Ticket scanner" description="Scan the ticket QR code or enter its token. Each valid ticket can be used once."/>
    <label className="scanner-event">Event<select value={eventId} onChange={(event) => setEventId(event.target.value)}><option value="">Choose an event</option>{events.map((event) => <option key={event.id} value={event.id}>{event.title}</option>)}</select></label>
    {eventId && <QRCodeScanner onScan={onScan}/>}
    <form className="scanner-manual" onSubmit={(event) => { event.preventDefault(); verify(); }}><label>Ticket QR token<input value={token} onChange={(event) => setToken(event.target.value)} autoComplete="off" placeholder="Scan QR or paste ticket token"/></label><button className="button button-primary">Verify ticket <Check size={16}/></button></form>
    <Notice error={error} message={result}/>
  </>;
}

function OrganizerAnalytics() {
  const { data: analytics, error, loading } = useData("/events/analytics", {});
  const { data: stats } = useData("/events/dashboard", {});
  if (loading) return <Loading/>;
  return <>
    <PageTitle eyebrow="EVENT PERFORMANCE" title="Analytics" description="Registration and revenue metrics from your live events."/>
    <MetricCards entries={Object.entries(stats)}/>
    <div className="charts-grid">
      <ChartCard title="Monthly registrations"><ResponsiveContainer width="100%" height={270}><LineChart data={analytics.monthly_registrations}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="month"/><YAxis allowDecimals={false}/><Tooltip/><Line dataKey="count" type="monotone" stroke="#6856dd" strokeWidth={3}/></LineChart></ResponsiveContainer></ChartCard>
      <ChartCard title="Registrations by event"><ResponsiveContainer width="100%" height={270}><BarChart data={analytics.event_registrations} layout="vertical"><CartesianGrid strokeDasharray="3 3" horizontal={false}/><XAxis type="number" allowDecimals={false}/><YAxis dataKey="event" type="category" width={120}/><Tooltip/><Bar dataKey="count" fill="#6856dd" radius={[0, 5, 5, 0]}/></BarChart></ResponsiveContainer></ChartCard>
      <ChartCard title="Monthly revenue"><ResponsiveContainer width="100%" height={270}><LineChart data={analytics.monthly_revenue}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="month"/><YAxis/><Tooltip formatter={(value) => `₹${value}`}/><Line dataKey="amount" type="monotone" stroke="#59a28e" strokeWidth={3}/></LineChart></ResponsiveContainer></ChartCard>
    </div>
  </>;
}

function NotificationsPanel() {
  const { data, error, loading, load } = useData("/notifications", {});
  async function markRead(item) {
    try {
      await api.put(`/notifications/${item.id}/read`);
      await load();
    } catch (requestError) {
      window.alert(errorMessage(requestError));
    }
  }
  return <>
    <PageTitle eyebrow="UPDATES" title="Notifications" description="Registration updates, event changes, and announcements."/>
    <Notice error={error}/>{loading ? <Loading/> : <div className="notification-list">{(data.items || []).map((item) => <article className={`notification-card${item.is_read ? " read" : ""}`} key={item.id}><span className="notification-icon"><Bell size={17}/></span><div><strong>{item.title}</strong><p>{item.message}</p><small>{new Date(item.created_at).toLocaleString()}</small></div>{!item.is_read && <button className="button button-quiet small" onClick={() => markRead(item)}>Mark read</button>}</article>)}</div>}
    {!data.items?.length && !loading && <div className="empty-state">You’re all caught up.</div>}
  </>;
}

function ProfilePanel({ user, setUser }) {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [fileBusy, setFileBusy] = useState(false);
  async function saveProfile(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const { data } = await api.patch("/auth/me", values);
      setUser(data.user);
      setMessage("Profile updated.");
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  async function changePassword(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setError("");
    setMessage("");
    const values = Object.fromEntries(new FormData(event.currentTarget));
    if (values.new_password !== values.confirm_password) {
      setError("New passwords do not match.");
      return;
    }
    try {
      const { data } = await api.put("/auth/me/password", values);
      setMessage(data.message);
      setUser(null);
      formElement.reset();
      navigate("/login", { replace: true });
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  async function uploadFile(field, endpoint = "/auth/me/profile-image", key = "file") {
    const input = document.getElementById(field);
    if (!input.files[0]) return setError("Choose a file first.");
    setError("");
    setFileBusy(true);
    const form = new FormData();
    form.append(key, input.files[0]);
    try {
      const { data } = await api.post(endpoint, form);
      setUser(data.user);
      setMessage("File uploaded.");
      input.value = "";
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setFileBusy(false);
    }
  }
  async function deleteAccount() {
    const confirmation = window.prompt("Type DELETE to permanently close this account.");
    if (confirmation !== "DELETE") return;
    try {
      await api.delete("/auth/me");
      await logout();
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  const organizer = user.role === "organizer";
  return <>
    <PageTitle eyebrow="ACCOUNT SETTINGS" title={organizer ? "Organization profile" : "Your profile"} description="Keep your contact details and account information up to date."/>
    <Notice error={error} message={message}/>
    <form className="profile-form form-panel" onSubmit={saveProfile}>
      <div className="profile-form-grid">
        <label>Full name<input name="full_name" maxLength="120" defaultValue={user.full_name} required/></label>
        <label>Email address<input value={user.email} disabled/></label>
        <label>Phone<input name="phone" maxLength="32" defaultValue={user.phone || ""}/></label>
        {organizer ? <>
          <label>Organization name<input name="organization_name" maxLength="160" defaultValue={user.organization_name || ""}/></label>
          <label className="span-two">Organization description<textarea name="organization_description" rows="3" defaultValue={user.organization_description || ""}/></label>
          <label className="span-two">Organization address<input name="organization_address" defaultValue={user.organization_address || ""}/></label>
        </> : <>
          <label>College / organization<input name="college_name" maxLength="180" defaultValue={user.college_name || ""}/></label>
          <label>Department<input name="department" maxLength="120" defaultValue={user.department || ""}/></label>
          <label>Student ID<input name="student_id" maxLength="80" defaultValue={user.student_id || ""}/></label>
        </>}
        <button className="button button-primary">Save profile</button>
      </div>
    </form>
    <section className="form-panel"><h2>Profile photo</h2>{user.profile_image && <img className="profile-image-preview" src={`${import.meta.env.VITE_API_URL || "http://localhost:5000/api"}/uploads/${encodeURIComponent(user.profile_image)}`} alt={`${user.full_name} profile`}/>}<div className="file-upload-row"><label>Choose image<input id="profile-image" type="file" accept="image/png,image/jpeg,image/webp"/></label><button className="button button-outline" disabled={fileBusy} onClick={() => uploadFile("profile-image")}>Upload image <Upload size={15}/></button></div></section>
    {organizer && <section className="form-panel"><h2>Organization verification files</h2><p className="form-help">Optional: add a logo and a supporting PDF or image for admin review. Files are limited to 5 MB.</p><div className="file-upload-row"><label>Organization logo<input id="organization-logo" type="file" accept="image/png,image/jpeg,image/webp"/></label><button className="button button-outline" disabled={fileBusy} onClick={() => uploadFile("organization-logo", "/auth/me/organization-files", "logo")}>Upload logo <Upload size={15}/></button></div><div className="file-upload-row"><label>Supporting document<input id="organization-document" type="file" accept="application/pdf,image/png,image/jpeg"/></label><button className="button button-outline" disabled={fileBusy} onClick={() => uploadFile("organization-document", "/auth/me/organization-files", "document")}>Upload document <Upload size={15}/></button></div></section>}
    <section className="form-panel"><h2>Change password</h2><form className="profile-form-grid" onSubmit={changePassword}><label>Current password<input name="current_password" type="password" autoComplete="current-password" required/></label><label>New password<input name="new_password" type="password" minLength="10" autoComplete="new-password" required/></label><label>Confirm new password<input name="confirm_password" type="password" minLength="10" autoComplete="new-password" required/></label><button className="button button-primary">Update password</button></form></section>
    {user.role !== "admin" && <section className="danger-zone"><div><h3>Delete account</h3><p>This action permanently removes your participant data. Organizers with event history must contact an administrator.</p></div><button className="button button-danger" onClick={deleteAccount}><Trash2 size={15}/> Delete account</button></section>}
  </>;
}
