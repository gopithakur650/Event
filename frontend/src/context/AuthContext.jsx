import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import api from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const { data } = await api.get("/auth/me");
    setUser(data.user);
    return data.user;
  }, []);

  useEffect(() => {
    refreshUser()
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, [refreshUser]);

  const value = useMemo(() => ({
    user,
    loading,
    setUser,
    async login(email, password, rememberMe = false) {
      const { data } = await api.post("/auth/login", {
        email,
        password,
        remember_me: rememberMe,
      });
      setUser(data.user);
    },
    async register(values) {
      return api.post("/auth/register", values);
    },
    async logout() {
      try {
        await api.post("/auth/logout");
      } finally {
        setUser(null);
      }
    },
    refreshUser,
  }), [user, loading, refreshUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
