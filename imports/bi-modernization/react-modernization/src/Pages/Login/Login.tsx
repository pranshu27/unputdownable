import React, { useMemo, useState } from 'react';
import { Box, Button, Typography } from '@mui/material';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Database,
  FileSearch,
  Lock,
  Mail,
  ShieldCheck,
  Sparkles,
  User,
} from 'lucide-react';
import Loader from '../../core/Loader/Loader.tsx';
import './Login.scss';

type AuthMode = 'login' | 'signup';

type FieldErrors = {
  email?: string;
  password?: string;
  fullName?: string;
  confirmPassword?: string;
};

const flowItems = [
  { icon: FileSearch, label: 'Upload and analyze', detail: 'PBIX, Tableau, Qlik, ETL, and database assets' },
  { icon: BarChart3, label: 'Explore workspace', detail: 'Overview, data sources, relationships, and models' },
  { icon: Sparkles, label: 'Govern and enrich', detail: 'Gap analysis, validation, KPI rationalization, and business enrichment' },
];

const trustItems = ['Validated workspace access', 'Analysis history retained', 'Curated metadata workflow'];

const Login = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const initialMode: AuthMode = location.pathname === '/signup' ? 'signup' : 'login';
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const isSignup = mode === 'signup';

  const pageCopy = useMemo(
    () => ({
      title: isSignup ? 'Create your workspace account' : 'Welcome back',
      subtitle: isSignup
        ? 'Set up access to the modernization workspace and start analyzing your assets.'
        : 'Sign in to continue your modernization, validation, and enrichment workflows.',
      button: isSignup ? 'Create account' : 'Sign in',
      switchPrompt: isSignup ? 'Already have access?' : 'Need a workspace account?',
      switchAction: isSignup ? 'Sign in' : 'Create one',
    }),
    [isSignup]
  );

  const updateMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setError('');
    setFieldErrors({});
    navigate(nextMode === 'signup' ? '/signup' : '/login', { replace: true });
  };

  const validate = () => {
    const nextErrors: FieldErrors = {};
    if (isSignup && !fullName.trim()) nextErrors.fullName = 'Full name is required';
    if (!email.trim()) nextErrors.email = 'Email is required';
    if (!password.trim()) nextErrors.password = 'Password is required';
    if (isSignup && password && password.length < 8) nextErrors.password = 'Use at least 8 characters';
    if (isSignup && confirmPassword !== password) nextErrors.confirmPassword = 'Passwords must match';
    setFieldErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const submit = async () => {
    if (!validate()) return;

    try {
      setLoading(true);
      setError('');
      localStorage.setItem('isLoggedIn', 'true');
      localStorage.setItem(
        'jnjUserProfile',
        JSON.stringify({
          name: fullName || 'J&J User',
          email,
          createdAt: new Date().toISOString(),
        })
      );
      navigate('/migration');
    } catch {
      setError('Unable to complete authentication. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const clearFieldError = (field: keyof FieldErrors) => {
    if (fieldErrors[field]) setFieldErrors((prev) => ({ ...prev, [field]: undefined }));
  };

  return (
    <Box className="jnj-auth-page">
      <section className="jnj-auth-brand">
        <div className="jnj-auth-brand__mark" aria-label="Johnson and Johnson">
          J&J
        </div>

        {/* Enterprise Visualization Mesh */}
        <div className="jnj-mesh-container">
          <svg width="100%" height="100%" viewBox="0 0 800 800" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
            <g className="jnj-mesh-float-1">
              <line x1="100" y1="200" x2="300" y2="150" className="jnj-mesh-line" />
              <line x1="300" y1="150" x2="500" y2="300" className="jnj-mesh-line jnj-mesh-line--active" />
              <line x1="500" y1="300" x2="700" y2="200" className="jnj-mesh-line" />
              <line x1="500" y1="300" x2="400" y2="500" className="jnj-mesh-line" />
              <line x1="400" y1="500" x2="200" y2="400" className="jnj-mesh-line jnj-mesh-line--active" />
              <line x1="200" y1="400" x2="100" y2="200" className="jnj-mesh-line" />
              
              <circle cx="100" cy="200" r="4" className="jnj-mesh-node" />
              <circle cx="300" cy="150" r="8" className="jnj-mesh-node jnj-mesh-node--secondary" />
              <circle cx="500" cy="300" r="12" className="jnj-mesh-node jnj-mesh-node--primary" />
              <circle cx="700" cy="200" r="6" className="jnj-mesh-node" />
              <circle cx="400" cy="500" r="10" className="jnj-mesh-node jnj-mesh-node--secondary" />
              <circle cx="200" cy="400" r="6" className="jnj-mesh-node" />
            </g>

            <g className="jnj-mesh-float-2">
              <line x1="150" y1="600" x2="350" y2="700" className="jnj-mesh-line jnj-mesh-line--active" />
              <line x1="350" y1="700" x2="600" y2="600" className="jnj-mesh-line" />
              <line x1="600" y1="600" x2="400" y2="500" className="jnj-mesh-line" />
              <line x1="600" y1="600" x2="750" y2="750" className="jnj-mesh-line" />
              
              <circle cx="150" cy="600" r="5" className="jnj-mesh-node" />
              <circle cx="350" cy="700" r="9" className="jnj-mesh-node jnj-mesh-node--primary" />
              <circle cx="600" cy="600" r="7" className="jnj-mesh-node" />
              <circle cx="750" cy="750" r="4" className="jnj-mesh-node" />
              
              {/* Floating semantic points */}
              <circle cx="450" cy="250" r="2" className="jnj-mesh-dot" />
              <circle cx="250" cy="450" r="2" className="jnj-mesh-dot" />
              <circle cx="550" cy="650" r="2" className="jnj-mesh-dot" />
              <circle cx="650" cy="350" r="2" className="jnj-mesh-dot" />
            </g>
            
            <g className="jnj-mesh-float-3">
              <line x1="650" y1="100" x2="750" y2="350" className="jnj-mesh-line" />
              <line x1="750" y1="350" x2="850" y2="200" className="jnj-mesh-line jnj-mesh-line--active" />
              
              <circle cx="650" cy="100" r="4" className="jnj-mesh-node" />
              <circle cx="750" cy="350" r="6" className="jnj-mesh-node jnj-mesh-node--secondary" />
              <circle cx="850" cy="200" r="5" className="jnj-mesh-node" />
            </g>
          </svg>
        </div>

        <div className="jnj-auth-tagline">
          <h1>Enterprise Metadata Intelligence</h1>
          <p>
            Validate, rationalize, and govern your analytics 
            ecosystem in one unified workspace.
          </p>
        </div>
      </section>

      <section className="jnj-auth-panel" aria-label={isSignup ? 'Sign up form' : 'Login form'}>
        <div className="jnj-auth-card">
          <div className="jnj-auth-card__header">
            <span className="jnj-auth-card__icon">
              {isSignup ? <User size={20} /> : <ShieldCheck size={20} />}
            </span>
            <div>
              <Typography component="h2" className="jnj-auth-card__title">
                {pageCopy.title}
              </Typography>
              <Typography className="jnj-auth-card__subtitle">{pageCopy.subtitle}</Typography>
            </div>
          </div>

          <div className="jnj-auth-toggle" role="tablist" aria-label="Authentication mode">
            <button
              type="button"
              role="tab"
              aria-selected={!isSignup}
              className={!isSignup ? 'is-active' : ''}
              onClick={() => updateMode('login')}
            >
              Login
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={isSignup}
              className={isSignup ? 'is-active' : ''}
              onClick={() => updateMode('signup')}
            >
              Sign up
            </button>
          </div>

          <div className="jnj-auth-fields">
            {isSignup && (
              <label className="jnj-auth-field" htmlFor="fullName">
                <span>Full name</span>
                <div className={`jnj-auth-input ${fieldErrors.fullName ? 'has-error' : ''}`}>
                  <User size={18} />
                  <input
                    id="fullName"
                    type="text"
                    placeholder="Enter your name"
                    value={fullName}
                    onChange={(event) => {
                      setFullName(event.target.value);
                      clearFieldError('fullName');
                    }}
                  />
                </div>
                {fieldErrors.fullName && <small className="jnj-auth-error">{fieldErrors.fullName}</small>}
              </label>
            )}

            <label className="jnj-auth-field" htmlFor="email">
              <span>Email</span>
              <div className={`jnj-auth-input ${fieldErrors.email ? 'has-error' : ''}`}>
                <Mail size={18} />
                <input
                  id="email"
                  type="email"
                  placeholder="name@jnj.com"
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    clearFieldError('email');
                  }}
                />
              </div>
              {fieldErrors.email && <small className="jnj-auth-error">{fieldErrors.email}</small>}
            </label>

            <label className="jnj-auth-field" htmlFor="password">
              <span>Password</span>
              <div className={`jnj-auth-input ${fieldErrors.password ? 'has-error' : ''}`}>
                <Lock size={18} />
                <input
                  id="password"
                  type="password"
                  placeholder="Enter password"
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    clearFieldError('password');
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !isSignup) submit();
                  }}
                />
              </div>
              {fieldErrors.password && <small className="jnj-auth-error">{fieldErrors.password}</small>}
            </label>

            {isSignup && (
              <label className="jnj-auth-field" htmlFor="confirmPassword">
                <span>Confirm password</span>
                <div className={`jnj-auth-input ${fieldErrors.confirmPassword ? 'has-error' : ''}`}>
                  <Lock size={18} />
                  <input
                    id="confirmPassword"
                    type="password"
                    placeholder="Confirm password"
                    value={confirmPassword}
                    onChange={(event) => {
                      setConfirmPassword(event.target.value);
                      clearFieldError('confirmPassword');
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') submit();
                    }}
                  />
                </div>
                {fieldErrors.confirmPassword && (
                  <small className="jnj-auth-error">{fieldErrors.confirmPassword}</small>
                )}
              </label>
            )}
          </div>

          {error && <p className="jnj-auth-error jnj-auth-error--form">{error}</p>}

          <Button className="jnj-auth-submit" fullWidth onClick={submit}>
            {pageCopy.button}
            <ArrowRight size={18} />
          </Button>

          <div className="jnj-auth-card__footer">
            <span>{pageCopy.switchPrompt}</span>
            <button type="button" onClick={() => updateMode(isSignup ? 'login' : 'signup')}>
              {pageCopy.switchAction}
            </button>
          </div>

          <div className="jnj-auth-trust">
            {trustItems.map((item) => (
              <span key={item}>
                <CheckCircle2 size={14} />
                {item}
              </span>
            ))}
          </div>
        </div>
      </section>

      <Loader show={loading} />
    </Box>
  );
};

export default Login;
