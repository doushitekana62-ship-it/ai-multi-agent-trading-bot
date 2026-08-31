import React from 'react';
import ReactDOM from 'react-dom/client';
import axios from 'axios';
import App from './App';

// Keep dashboard requests bounded so a slow API call cannot leave controls
// waiting indefinitely. Paper scheduling is server-side in the Durable Object;
// the browser never runs trading cycles or intercepts the React control events.
axios.defaults.timeout = 10000;

const root = ReactDOM.createRoot(
  document.getElementById('root')
);

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
