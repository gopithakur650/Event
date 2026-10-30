import React, { useEffect, useState } from "react";
import { ArrowRight, CalendarDays, Check, Compass, Ticket, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { EventCard, Notice } from "../components/shared";
import api, { errorMessage } from "../services/api";

const CATEGORY_DESCRIPTIONS = {
  "Technical Events": "Fresh ideas and future-facing technology.",
  "Cultural Events": "Celebrate creativity and community.",
  Workshops: "Learn something by doing it.",
  Seminars: "Meet ideas worth sharing.",
  "Sports Events": "Bring your team and find your game.",
  "Music and Entertainment": "Find the soundtrack to your next night out.",
  Conferences: "Connect with people shaping what comes next.",
  Competitions: "Show what you can do.",
  "Other Events": "A little bit of everything.",
};

export default function Home() {
  const [events, setEvents] = useState([]);
  const [categories, setCategories] = useState([]);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [contactError, setContactError] = useState("");
  const [contactMessage, setContactMessage] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get("/events/featured"),
      api.get("/events/categories"),
      api.get("/events/stats"),
    ]).then(([eventResponse, categoryResponse, statsResponse]) => {
      setEvents(eventResponse.data.items);
      setCategories(categoryResponse.data.items);
      setStats(statsResponse.data);
    }).catch((requestError) => setError(errorMessage(requestError)));
  }, []);

  async function sendContact(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setContactError("");
    setContactMessage("");
    setSending(true);
    try {
      const values = Object.fromEntries(new FormData(event.currentTarget));
      const { data } = await api.post("/events/contact", values);
      setContactMessage(data.message);
      formElement.reset();
    } catch (requestError) {
      setContactError(errorMessage(requestError));
    } finally {
      setSending(false);
    }
  }

  return <>
    <section className="hero">
      <div className="hero-copy">
        <span className="pill"><span className="pulse"/> Your next great story starts here</span>
        <h1>Find your people.<br/><em>Make it an event.</em></h1>
        <p>Discover experiences worth showing up for, or bring your own community together.</p>
        <div className="hero-actions">
          <Link className="button button-primary" to="/events">Explore events <ArrowRight size={17}/></Link>
          <Link className="button button-outline" to="/register?role=organizer">Host an event</Link>
        </div>
        <div className="hero-trust"><div className="avatar-stack"><b>A</b><b>M</b><b>J</b></div><span>Made for communities that bring people together</span></div>
      </div>
      <div className="hero-visual">
        <div className="orbit orbit-one"/><div className="orbit orbit-two"/>
        <div className="visual-card visual-main">
          <div className="visual-icon"><CalendarDays size={25}/></div>
          <span className="eyebrow">YOUR NEXT PLAN</span><h3>Good things, together.</h3>
          <p>Find a community event and make it yours.</p>
          <div className="visual-bottom"><div className="avatar-stack"><b>L</b><b>R</b><b>+</b></div><span>Find events near you</span></div>
        </div>
        <div className="floating-note"><span className="note-icon"><Check size={16}/></span><div><strong>One less thing to plan</strong><small>Tickets live in your account</small></div></div>
        <div className="floating-date"><strong>◎</strong><span>GATHER</span></div>
      </div>
    </section>

    <section className="stats">
      <div><strong>Good things</strong><span>happen when we get together</span></div>
      <div><Compass/><strong>{stats?.events ?? "—"}</strong><span>upcoming events</span></div>
      <div><Users/><strong>{stats?.participants ?? "—"}</strong><span>participants</span></div>
      <div><Ticket/><strong>{stats?.registrations ?? "—"}</strong><span>confirmed registrations</span></div>
    </section>

    <section className="section" id="about">
      <div className="section-heading">
        <div><span className="eyebrow purple">GOOD THINGS AHEAD</span><h2>Events worth your time</h2><p>Find something new to look forward to.</p></div>
        <Link className="text-link" to="/events">See all events <ArrowRight size={16}/></Link>
      </div>
      {error && <Notice error={error}/>}
      <div className="event-grid">{events.map((event) => <EventCard key={event.id} event={event}/>)}</div>
      {!error && events.length === 0 && <div className="empty-state">New experiences are on the way. Check back soon.</div>}
    </section>

    <section className="section categories-section">
      <div className="section-heading"><div><span className="eyebrow purple">FOLLOW YOUR CURIOSITY</span><h2>Find your kind of gathering</h2><p>From hands-on workshops to nights out, there’s room for every interest.</p></div></div>
      <div className="category-grid">{categories.map((category, index) => <Link className="category-card" to={`/events?category=${encodeURIComponent(category.name)}`} key={category.id}>
        <span className={`category-icon category-${index % 5}`}><CalendarDays size={19}/></span>
        <strong>{category.name}</strong><small>{CATEGORY_DESCRIPTIONS[category.name] || "Discover the next event for you."}</small><ArrowRight size={16}/>
      </Link>)}</div>
    </section>

    <section className="how-section">
      <div><span className="eyebrow purple">MADE EASY</span><h2>Good plans, three simple steps.</h2></div>
      <div className="how-grid">
        <article><span>01</span><h3>Find your thing</h3><p>Search local events by date, category, format, or price.</p></article>
        <article><span>02</span><h3>Save your spot</h3><p>Register for a free event or pay securely for a ticket.</p></article>
        <article><span>03</span><h3>Show up and enjoy</h3><p>Your ticket and event updates are right in your account.</p></article>
      </div>
    </section>

    <section className="host-cta">
      <div className="host-icon"><CalendarDays/></div>
      <div><span className="eyebrow">HAVE SOMETHING TO SHARE?</span><h2>Good things happen when you bring people together.</h2><p>Create an event for your community. Your event goes live after a quick admin review.</p></div>
      <Link className="button button-light" to="/register?role=organizer">Start hosting <ArrowRight size={17}/></Link>
    </section>

    <section className="contact-section" id="contact">
      <div><span className="eyebrow purple">SAY HELLO</span><h2>We’re here to help.</h2><p>Send the Gatherly team a message and we’ll get back to you.</p></div>
      <form className="contact-form" onSubmit={sendContact}>
        <label>Your name<input name="name" required maxLength="100"/></label>
        <label>Email address<input name="email" type="email" required maxLength="255"/></label>
        <label className="span-two">Message<textarea name="message" rows="4" required maxLength="5000"/></label>
        <button className="button button-primary" disabled={sending}>{sending ? "Sending…" : "Send message"} <ArrowRight size={16}/></button>
        <Notice error={contactError} message={contactMessage}/>
      </form>
    </section>

    <footer><Link className="brand" to="/"><span className="brand-mark">g</span> gatherly</Link><span>Make room for good things.</span><span>© {new Date().getFullYear()} Gatherly</span></footer>
  </>;
}
