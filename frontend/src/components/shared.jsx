import React, { useEffect, useState } from "react";
import { ArrowRight, Bell, LogOut, Search } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import api, { errorMessage } from "../services/api";

export function Brand() {
  return <Link className="brand" to="/"><span className="brand-mark">g</span> gatherly</Link>;
}

export function Header() {
  const { user, logout } = useAuth();
  const [error, setError] = useState("");
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (user) {
      api.get("/notifications")
        .then(({ data }) => setUnread(data.items.filter((item) => !item.is_read).length))
        .catch(() => {});
    } else {
      setUnread(0);
    }
  }, [user]);

  async function signOut() {
    setError("");
    try {
      await logout();
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }

  return <header className="topbar">
    <Brand />
    <nav aria-label="Main navigation">
      <Link to="/">Home</Link>
      <Link to="/events">Explore events</Link>
      <a href="/#about">About</a>
      <a href="/#contact">Contact</a>
      {user && <Link to="/dashboard">Dashboard</Link>}
    </nav>
    <div className="header-actions">
      {user ? <>
        <Link className="notification-link" to="/dashboard?tab=notifications" aria-label="Notifications">
          <Bell size={17} />{unread > 0 && <span>{unread}</span>}
        </Link>
        <Link className="user-name" to="/dashboard?tab=profile">{user.full_name}</Link>
        <button className="button button-quiet" onClick={signOut}><LogOut size={16}/> Sign out</button>
      </> : <>
        <Link className="button button-quiet" to="/login">Log in</Link>
        <Link className="button button-primary small" to="/register">Get started</Link>
      </>}
    </div>
    {error && <span className="header-error" role="status">{error}</span>}
  </header>;
}

export function EventCard({ event }) {
  const poster = event.poster
    ? `${import.meta.env.VITE_API_URL || "http://localhost:5000/api"}/uploads/${encodeURIComponent(event.poster)}`
    : null;
  return <article className="event-card">
    <Link to={`/events/${event.id}`} className="event-card-link" aria-label={`View ${event.title}`}>
      <div className={`event-art${poster ? " has-poster" : ""}`}>
        {poster ? <img src={poster} alt={`${event.title} poster`} /> : <Search size={30}/>}
        <span>{event.category?.name || "Event"}</span>
      </div>
      <div className="event-card-body">
        <div className="eyebrow">{new Date(event.start_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })} · {event.city || event.venue || "Online"}</div>
        <h3>{event.title}</h3>
        <p>{event.description}</p>
        <div className="event-card-foot">
          <span>{event.fee ? `₹${event.fee}` : "Free"} · {event.available_seats} seats left</span>
          <span className="event-card-arrow"><ArrowRight size={17}/></span>
        </div>
      </div>
    </Link>
  </article>;
}

export function Notice({ error, message }) {
  if (!error && !message) return null;
  return <div className={`notice ${error ? "error" : "success"}`} role={error ? "alert" : "status"}>
    {error || message}
  </div>;
}

export function Loading({ children = "Loading…" }) {
  return <div className="loading" role="status">{children}</div>;
}

export function PageTitle({ eyebrow, title, description, action }) {
  return <div className="section-heading page-title">
    <div>
      {eyebrow && <span className="eyebrow purple">{eyebrow}</span>}
      <h1>{title}</h1>
      {description && <p>{description}</p>}
    </div>
    {action}
  </div>;
}

export function StatusPill({ value }) {
  const text = (value || "unknown").replaceAll("_", " ");
  return <span className={`status-pill status-${(value || "").replaceAll("_", "-")}`}>{text}</span>;
}
