import React, { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Header, Loading } from "./components/shared";
import { useAuth } from "./context/AuthContext";
import { Link } from "react-router-dom";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const EventsPage = lazy(() => import("./pages/EventsPage").then((module) => ({ default: module.EventsPage })));
const EventDetailsPage = lazy(() => import("./pages/EventsPage").then((module) => ({ default: module.EventDetailsPage })));
const AuthPage = lazy(() => import("./pages/AuthPages").then((module) => ({ default: module.AuthPage })));
const ForgotPasswordPage = lazy(() => import("./pages/AuthPages").then((module) => ({ default: module.ForgotPasswordPage })));
const ResetPasswordPage = lazy(() => import("./pages/AuthPages").then((module) => ({ default: module.ResetPasswordPage })));
const Home = lazy(() => import("./pages/Home"));
function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading>Loading your account…</Loading>;
  return user ? children : <Navigate to="/login" replace/>;
}

export default function App() {
  const { loading } = useAuth();
  if (loading) return <Loading>Loading Gatherly…</Loading>;
  return <><Header/><Suspense fallback={<Loading/>}><Routes>
    <Route path="/" element={<Home/>}/>
    <Route path="/events" element={<EventsPage/>}/>
    <Route path="/events/:id" element={<EventDetailsPage/>}/>
    <Route path="/login" element={<AuthPage/>}/>
    <Route path="/register" element={<AuthPage register/>}/>
    <Route path="/forgot-password" element={<ForgotPasswordPage/>}/>
    <Route path="/reset-password" element={<ResetPasswordPage/>}/>
    <Route path="/dashboard" element={<Protected><Dashboard/></Protected>}/>
    <Route path="*" element={<main className="page"><h1>Page not found</h1><Link to="/">Back home</Link></main>}/>
  </Routes></Suspense></>;
}
