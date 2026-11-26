"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { fetchCapabilities, type Capabilities } from "@/lib/api";
import {
  getIdToken,
  isSupabaseConfigured,
  observeAuth,
  signIn as supabaseSignIn,
  signOut as supabaseSignOut,
  signUp as supabaseSignUp,
  type SignUpResult,
  type SupabaseUser,
} from "@/lib/supabase";

type AuthContextValue = {
  user: SupabaseUser | null;
  capabilities: Capabilities | null;
  supabaseReady: boolean;
  authLoading: boolean;
  token: string | null;
  refreshToken: () => Promise<string | null>;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<SignUpResult>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SupabaseUser | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);

  const refreshToken = useCallback(async () => {
    const next = await getIdToken();
    setToken(next);
    return next;
  }, []);

  useEffect(() => {
    const unsubscribe = observeAuth((nextUser) => {
      setUser(nextUser);
      setAuthLoading(false);
      void getIdToken().then(setToken);
    });
    let mounted = true;
    fetchCapabilities()
      .then((value) => {
        if (mounted) setCapabilities(value);
      })
      .catch(() => {
        if (mounted) setCapabilities(null);
      });
    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []);

  const signIn = useCallback(
    async (email: string, password: string) => {
      await supabaseSignIn(email, password);
      await refreshToken();
    },
    [refreshToken],
  );

  const signUp = useCallback(
    async (email: string, password: string) => {
      const result = await supabaseSignUp(email, password);
      await refreshToken();
      return result;
    },
    [refreshToken],
  );

  const signOut = useCallback(async () => {
    await supabaseSignOut();
    setToken(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      capabilities,
      supabaseReady: isSupabaseConfigured(),
      authLoading,
      token,
      refreshToken,
      signIn,
      signUp,
      signOut,
    }),
    [user, capabilities, authLoading, token, refreshToken, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
