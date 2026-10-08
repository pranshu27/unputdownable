import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";

import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Provider } from 'react-redux';
import { store } from './utils/Store.ts';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ThemeProvider as JnjThemeProvider } from './utils/ThemeContext.tsx';

const queryClient = new QueryClient();
const theme = createTheme();

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <JnjThemeProvider>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Provider store={store}>
          <QueryClientProvider client={queryClient}>
            <App />
          </QueryClientProvider>
        </Provider>
      </ThemeProvider>
    </JnjThemeProvider>
  </React.StrictMode>
);

// For performance measurement
reportWebVitals();
