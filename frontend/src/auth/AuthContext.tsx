import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { CognitoUserPool, CognitoUser, AuthenticationDetails, CognitoUserSession } from 'amazon-cognito-identity-js';
import { getConfig } from '../config';

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: CognitoUser | null;
  error: string | null;
}

interface AuthContextType extends AuthState {
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  completeNewPassword: (newPassword: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

function getUserPool(): CognitoUserPool {
  const config = getConfig();
  return new CognitoUserPool({
    UserPoolId: config.cognitoUserPoolId,
    ClientId: config.cognitoClientId,
  });
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    user: null,
    error: null,
  });
  const [pendingUser, setPendingUser] = useState<CognitoUser | null>(null);

  useEffect(() => {
    const pool = getUserPool();
    const currentUser = pool.getCurrentUser();
    if (currentUser) {
      currentUser.getSession((err: Error | null, session: CognitoUserSession | null) => {
        if (err || !session?.isValid()) {
          setState({ isAuthenticated: false, isLoading: false, user: null, error: null });
        } else {
          setState({ isAuthenticated: true, isLoading: false, user: currentUser, error: null });
        }
      });
    } else {
      setState(s => ({ ...s, isLoading: false }));
    }
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    setState(s => ({ ...s, error: null, isLoading: true }));
    const pool = getUserPool();
    const user = new CognitoUser({ Username: email, Pool: pool });
    const authDetails = new AuthenticationDetails({ Username: email, Password: password });

    return new Promise<void>((resolve, reject) => {
      user.authenticateUser(authDetails, {
        onSuccess: () => {
          setState({ isAuthenticated: true, isLoading: false, user, error: null });
          resolve();
        },
        onFailure: (err) => {
          setState({ isAuthenticated: false, isLoading: false, user: null, error: err.message });
          reject(err);
        },
        newPasswordRequired: () => {
          setPendingUser(user);
          setState(s => ({ ...s, isLoading: false, error: 'NEW_PASSWORD_REQUIRED' }));
          resolve();
        },
      });
    });
  }, []);

  const completeNewPassword = useCallback(async (newPassword: string) => {
    if (!pendingUser) return;
    setState(s => ({ ...s, isLoading: true, error: null }));
    return new Promise<void>((resolve, reject) => {
      pendingUser.completeNewPasswordChallenge(newPassword, {}, {
        onSuccess: () => {
          setState({ isAuthenticated: true, isLoading: false, user: pendingUser, error: null });
          setPendingUser(null);
          resolve();
        },
        onFailure: (err) => {
          setState(s => ({ ...s, isLoading: false, error: err.message }));
          reject(err);
        },
      });
    });
  }, [pendingUser]);

  const signOut = useCallback(() => {
    const pool = getUserPool();
    const currentUser = pool.getCurrentUser();
    currentUser?.signOut();
    setState({ isAuthenticated: false, isLoading: false, user: null, error: null });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, signIn, signOut, completeNewPassword }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
