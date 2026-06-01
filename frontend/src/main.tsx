import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import '@syncfusion/ej2-base/styles/tailwind.css';
import '@syncfusion/ej2-buttons/styles/tailwind.css';
import '@syncfusion/ej2-inputs/styles/tailwind.css';
import '@syncfusion/ej2-popups/styles/tailwind.css';
import '@syncfusion/ej2-lists/styles/tailwind.css';
import '@syncfusion/ej2-navigations/styles/tailwind.css';
import '@syncfusion/ej2-splitbuttons/styles/tailwind.css';
import '@syncfusion/ej2-dropdowns/styles/tailwind.css';
import '@syncfusion/ej2-documenteditor/styles/tailwind.css';
import '@syncfusion/ej2-react-documenteditor/styles/tailwind.css';
import 'pdfjs-dist/web/pdf_viewer.css';
import App from './App.tsx';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
