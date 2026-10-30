import React, { useState } from "react";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Brand, Notice } from "../components/shared";
import { useAuth } from "../context/AuthContext";
import api, { errorMessage } from "../services/api";

function AuthShell({ eyebrow, title, description, children }) {
  return <main className="auth-page">
    <div className="auth-card">
      <Brand />
      <span className="eyebrow purple">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{description}</p>
      {children}
    </div>
    <aside className="auth-aside">
      <ShieldCheck size={23}/>
      <h2>Make room for good things.</h2>
      <p>Thoughtful gatherings start with a simple hello. Find events, meet your community, and make the most of being there.</p>
    </aside>
  </main>;
}

export function AuthPage({ register = false }) {
  const { login, register: signUp } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [role, setRole] = useState(params.get("role") === "organizer" ? "organizer" : "user");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setBusy(true);
    const form = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if (register) {
        if (form.password !== form.confirm_password) {
          setError("Passwords do not match.");
          return;
        }
        delete form.confirm_password;
        delete form.terms;
        await signUp({ ...form, role });
        setMessage(role === "organizer"
          ? "Your application is submitted. Sign in after an administrator approves your organizer account."
          : "Account created. You can now sign in.");
      } else {
        await login(form.email, form.password, form.remember_me === "on");
        const returnTo = params.get("returnTo");
        const destination = returnTo?.startsWith("/") && !returnTo.startsWith("//")
          ? returnTo
          : "/dashboard";
        navigate(destination, { replace: true });
      }
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  return <AuthShell
    eyebrow={register ? "YOUR NEXT CHAPTER" : "WELCOME BACK"}
    title={register ? "Join the good things." : "Good to see you."}
    description={register ? "Create an account to find or host your next event." : "Sign in to pick up where you left off."}
  >
    {register && <div className="role-switch" aria-label="Account type">
      <button type="button" className={role === "user" ? "selected" : ""} onClick={() => setRole("user")}>Participant</button>
      <button type="button" className={role === "organizer" ? "selected" : ""} onClick={() => setRole("organizer")}>Organizer</button>
    </div>}
    <form onSubmit={submit} className="form-stack">
      {register && <label>Full name<input name="full_name" maxLength="120" required autoComplete="name"/></label>}
      {register && role === "organizer" && <>
        <label>Organization name<input name="organization_name" maxLength="160" required/></label>
        <label>Organization description<textarea name="organization_description" maxLength="2000" rows="3"/></label>
        <label>Organization address<input name="organization_address" maxLength="255"/></label>
      </>}
      <label>Email address<input name="email" type="email" required autoComplete="email"/></label>
      {register && <label>Phone number<input name="phone" type="tel" maxLength="32" autoComplete="tel" required/></label>}
      {!register && <label className="check-label"><input name="remember_me" type="checkbox"/> Remember me for 30 days</label>}
      <label>Password<input name="password" type="password" minLength={register ? 8 : 1} required autoComplete={register ? "new-password" : "current-password"}/></label>
      {register && <label>Confirm password<input name="confirm_password" type="password" minLength="8" required autoComplete="new-password"/></label>}
      {register && <label className="check-label"><input name="terms" type="checkbox" required/> I agree to the terms and privacy policy</label>}
      <button className="button button-primary full" disabled={busy}>{busy ? "Please wait…" : register ? "Create account" : "Sign in"} <ArrowRight size={17}/></button>
    </form>
    {!register && <Link className="forgot-link" to="/forgot-password">Forgot your password?</Link>}
    <Notice error={error} message={message}/>
    <div className="auth-switch">{register ? "Already have an account?" : "New to Gatherly?"} <Link to={register ? "/login" : "/register"}>{register ? "Sign in" : "Create account"}</Link></div>
  </AuthShell>;
}

export function ForgotPasswordPage() {
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      const { data } = await api.post("/auth/forgot-password", {
        email: new FormData(event.currentTarget).get("email"),
      });
      setMessage(data.message);
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  return <AuthShell eyebrow="ACCOUNT RECOVERY" title="Reset your password." description="If the email belongs to an account, we’ll send a time-limited reset link.">
    <form className="form-stack" onSubmit={submit}>
      <label>Email address<input type="email" name="email" autoComplete="email" required/></label>
      <button className="button button-primary full">Send reset link <ArrowRight size={17}/></button>
    </form>
    <Notice error={error} message={message}/>
    <div className="auth-switch"><Link to="/login">Back to sign in</Link></div>
  </AuthShell>;
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function submit(event) {
    event.preventDefault();
    setError("");
    const form = Object.fromEntries(new FormData(event.currentTarget));
    if (form.password !== form.confirm_password) {
      setError("Passwords do not match.");
      return;
    }
    try {
      const { data } = await api.post("/auth/reset-password", {
        token: params.get("token"),
        password: form.password,
      });
      setMessage(data.message);
      setTimeout(() => navigate("/login", { replace: true }), 1200);
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }
  return <AuthShell eyebrow="ACCOUNT RECOVERY" title="Choose a new password." description="Use a strong password of at least 10 characters.">
    <form className="form-stack" onSubmit={submit}>
      <label>New password<input type="password" name="password" minLength="10" autoComplete="new-password" required/></label>
      <label>Confirm new password<input type="password" name="confirm_password" minLength="10" autoComplete="new-password" required/></label>
      <button className="button button-primary full">Reset password <ArrowRight size={17}/></button>
    </form>
    <Notice error={error} message={message}/>
  </AuthShell>;
}
