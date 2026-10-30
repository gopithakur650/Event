import React, { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, CalendarDays, Compass, Search, ShieldCheck, Users } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { EventCard, Notice, PageTitle } from "../components/shared";
import { useAuth } from "../context/AuthContext";
import api, { errorMessage } from "../services/api";

export function EventsPage() {
  const [params, setParams] = useSearchParams();
  const [events, setEvents] = useState([]);
  const [categories, setCategories] = useState([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const filters = Object.fromEntries(params);
      const [eventResponse, categoryResponse] = await Promise.all([
        api.get("/events", { params: { ...filters, page, per_page: 9 } }),
        api.get("/events/categories"),
      ]);
      setEvents(eventResponse.data.items);
      setPages(eventResponse.data.pages);
      setTotal(eventResponse.data.total);
      setCategories(categoryResponse.data.items);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [params, page]);

  useEffect(() => { load(); }, [load]);

  function setFilter(key, value) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
    setPage(1);
  }

  function search(event) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setFilter("search", values.get("search").trim());
  }

  return <main className="page">
    <PageTitle eyebrow="DISCOVER" title="Explore events" description="Find the experiences and people you’ll remember."/>
    <form className="search-bar" onSubmit={search}>
      <Search size={20}/>
      <input aria-label="Search events" name="search" placeholder="Search events, ideas, or places…" defaultValue={params.get("search") || ""}/>
      <button className="button button-primary small">Search</button>
    </form>
    <div className="filter-toolbar">
      <label>Category<select aria-label="Filter by category" value={params.get("category") || ""} onChange={(event) => setFilter("category", event.target.value)}>
        <option value="">All categories</option>{categories.map((category) => <option key={category.id} value={category.name}>{category.name}</option>)}
      </select></label>
      <label>Format<select value={params.get("event_type") || ""} onChange={(event) => setFilter("event_type", event.target.value)}>
        <option value="">Any format</option><option value="offline">In person</option><option value="online">Online</option><option value="hybrid">Hybrid</option>
      </select></label>
      <label>Price<select value={params.get("price") || ""} onChange={(event) => setFilter("price", event.target.value)}>
        <option value="">Any price</option><option value="free">Free</option><option value="paid">Paid</option>
      </select></label>
      <label>From<input type="date" value={params.get("date_from") || ""} onChange={(event) => setFilter("date_from", event.target.value)}/></label>
      <label>To<input type="date" value={params.get("date_to") || ""} onChange={(event) => setFilter("date_to", event.target.value)}/></label>
      <label>Sort<select value={params.get("sort") || "upcoming"} onChange={(event) => setFilter("sort", event.target.value)}>
        <option value="upcoming">Upcoming</option><option value="newest">Newest</option><option value="popular">Popular</option>
      </select></label>
      {params.size > 0 && <button className="button button-quiet" onClick={() => { setParams({}); setPage(1); }}>Clear filters</button>}
    </div>
    <div className="results-caption">{total} event{total === 1 ? "" : "s"} found</div>
    {error && <Notice error={error}/>}
    {loading ? <div className="loading">Finding events…</div> : <>
      <div className="event-grid">{events.map((event) => <EventCard key={event.id} event={event}/>)}</div>
      {!events.length && !error && <div className="empty-state">No events match those filters. Try broadening your search.</div>}
      {pages > 1 && <div className="pagination">
        <button className="button button-quiet" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ArrowLeft size={16}/> Previous</button>
        <span>Page {page} of {pages}</span>
        <button className="button button-quiet" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Next <ArrowRight size={16}/></button>
      </div>}
    </>}
    <Link className="back-home" to="/"><ArrowLeft size={15}/> Back home</Link>
  </main>;
}

export function EventDetailsPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [event, setEvent] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [alreadyRegistered, setAlreadyRegistered] = useState(false);

  useEffect(() => {
    api.get(`/events/${id}`).then(({ data }) => setEvent(data.event)).catch((requestError) => setError(errorMessage(requestError)));
  }, [id]);

  async function register() {
    if (!user) return navigate(`/login?returnTo=${encodeURIComponent(location.pathname)}`);
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const { data } = await api.post("/registrations", { event_id: event.id });
      if (data.checkout) {
        const razorpay = await loadRazorpay();
        const checkout = new razorpay({
          key: data.checkout.key_id,
          amount: data.checkout.amount,
          currency: data.checkout.currency,
          name: "Gatherly",
          description: event.title,
          order_id: data.checkout.order_id,
          prefill: data.checkout.prefill,
          theme: { color: "#6856dd" },
          handler: async (response) => {
            try {
              await api.post("/payments/verify", response);
              setAlreadyRegistered(true);
              setMessage("Payment verified. Your ticket is ready in your dashboard.");
            } catch (requestError) {
              setError(errorMessage(requestError));
            } finally {
              setBusy(false);
            }
          },
          modal: { ondismiss: () => setBusy(false) },
        });
        checkout.open();
        return;
      }
      setAlreadyRegistered(true);
      setMessage("You’re registered. Your ticket is ready in your dashboard.");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  if (error && !event) return <main className="page"><Notice error={error}/></main>;
  if (!event) return <main className="page"><div className="loading">Loading event…</div></main>;
  const poster = event.poster ? `${import.meta.env.VITE_API_URL || "http://localhost:5000/api"}/uploads/${encodeURIComponent(event.poster)}` : null;
  const venueAddress = [event.venue, event.address, event.city, event.state, event.postal_code].filter(Boolean).join(", ");
  return <main className="page detail-layout">
    <div>
      <div className={`detail-art${poster ? " has-poster" : ""}`}>
        {poster && <img src={poster} alt={`${event.title} event poster`}/>}
        <span>{event.category?.name}</span>
      </div>
      <span className="eyebrow purple">{event.category?.name} · {event.event_type}</span>
      <h1>{event.title}</h1>
      <p className="detail-description">{event.description}</p>
      <div className="detail-facts">
        <div><CalendarDays/><span><b>{new Date(event.start_at).toLocaleString()}</b><small>Until {new Date(event.end_at).toLocaleString()}</small></span></div>
        <div><Compass/><span><b>{venueAddress || "Online event"}</b><small>{event.event_type}</small></span></div>
        <div><Users/><span><b>{event.organizer_details?.name || event.organizer}</b><small>Event organizer</small></span></div>
        {event.eligibility && <div><ShieldCheck/><span><b>Eligibility</b><small>{event.eligibility}</small></span></div>}
      </div>
      {event.event_rules && <section className="detail-section"><h2>Event rules</h2><p>{event.event_rules}</p></section>}
      {event.required_materials && <section className="detail-section"><h2>What to bring</h2><p>{event.required_materials}</p></section>}
      {event.contact_email && <section className="detail-section"><h2>Questions?</h2><p><a href={`mailto:${event.contact_email}`}>{event.contact_email}</a>{event.contact_phone && ` · ${event.contact_phone}`}</p></section>}
      {event.website && <p><a className="text-link" href={event.website} target="_blank" rel="noreferrer">Event website <ArrowRight size={15}/></a></p>}
    </div>
    <aside className="registration-panel">
      <span className="eyebrow">SAVE YOUR SPOT</span><h2>{event.fee ? `₹${event.fee}` : "Free"}</h2>
      <p>{event.available_seats} spot{event.available_seats === 1 ? "" : "s"} available</p>
      {alreadyRegistered
        ? <Link className="button button-primary full" to="/dashboard?tab=registrations">View my ticket <ArrowRight size={17}/></Link>
        : <button className="button button-primary full" onClick={register} disabled={busy || !event.available_seats}>{busy ? "Please wait…" : event.available_seats ? "Register now" : "Event is full"} <ArrowRight size={17}/></button>}
      <Notice error={error} message={message}/>
      <small>Registration closes {new Date(event.registration_deadline).toLocaleString()}</small>
    </aside>
  </main>;
}

async function loadRazorpay() {
  if (window.Razorpay) return window.Razorpay;
  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = resolve;
    script.onerror = () => reject(new Error("Payment checkout could not be loaded."));
    document.body.append(script);
  });
  return window.Razorpay;
}
