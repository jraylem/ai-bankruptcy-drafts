# AI Petition Reviewer - Frontend

A modern React + TypeScript + Tailwind CSS application for AI-powered petition review and analysis.

## Tech Stack

- **React 19** - Latest React with improved performance
- **TypeScript** - Type-safe code with strict mode enabled
- **Vite** - Lightning-fast build tool and dev server
- **Tailwind CSS** - Utility-first CSS framework
- **Zustand** - Lightweight state management
- **Axios** - HTTP client for API requests
- **React Markdown** - Markdown rendering with GitHub Flavored Markdown support
- **PDF.js** - PDF viewing and rendering

## Project Structure

```
root/
├── src/
│   ├── assets/          # Static assets (images, icons)
│   ├── components/      # React components
│   │   ├── auth/        # Authentication components
│   │   ├── chat/        # Chat interface components
│   │   ├── common/      # Reusable UI components
│   │   ├── layout/      # Layout components
│   │   └── pdf/         # PDF viewer components
│   ├── constants/       # Application constants
│   ├── contexts/        # React contexts (if needed)
│   ├── hooks/           # Custom React hooks
│   ├── services/        # API service layer
│   │   ├── api.ts       # Base API configuration
│   │   ├── auth.service.ts
│   │   ├── chat.service.ts
│   │   └── pdf.service.ts
│   ├── stores/          # Zustand stores
│   │   ├── useAuthStore.ts
│   │   ├── useChatStore.ts
│   │   └── usePDFStore.ts
│   ├── types/           # TypeScript type definitions
│   ├── utils/           # Utility functions
│   ├── App.tsx          # Main application component
│   ├── main.tsx         # Application entry point
│   └── index.css        # Global styles with Tailwind
├── .env                 # Environment variables
├── .env.example         # Environment variables example
├── .prettierrc          # Prettier configuration
├── eslint.config.js     # ESLint configuration
├── tailwind.config.js   # Tailwind CSS configuration
├── tsconfig.json        # TypeScript configuration
├── vite.config.ts       # Vite configuration
└── package.json         # Project dependencies

```

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn

### Installation

1. Clone the repository and navigate to the project:
   ```bash
   cd root
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```

4. Update environment variables in `.env`:
   ```env
   VITE_API_URL=http://localhost:8000
   VITE_APP_NAME=AI Petition Reviewer
   ```

### Development

Start the development server:
```bash
npm run dev
```

The application will be available at `http://localhost:3000`

### Build

Build for production:
```bash
npm run build
```

Preview production build:
```bash
npm run preview
```

### Code Quality

Run ESLint:
```bash
npm run lint
```

Format code with Prettier:
```bash
npx prettier --write src/
```

## Features

### Authentication
- Secure login with JWT tokens
- Protected routes
- Persistent authentication state
- Automatic token refresh

### Chat Interface
- Real-time chat with AI assistant
- Markdown rendering for AI responses
- Message history
- Auto-scroll to latest message
- Loading states and error handling

### PDF Management
- PDF upload with validation
- File size and type checking
- PDF viewer integration (to be implemented)
- Page navigation and zoom controls

### UI Components
- Reusable component library
- Responsive design
- Loading states
- Error handling
- Accessible forms

## State Management

The application uses Zustand for state management with separate stores for:

- **Auth Store** (`useAuthStore`) - User authentication and session management
- **Chat Store** (`useChatStore`) - Chat messages and conversation state
- **PDF Store** (`usePDFStore`) - PDF document management and viewer state

## API Integration

API services are organized by feature:

- **api.ts** - Base Axios configuration with interceptors
- **auth.service.ts** - Authentication endpoints
- **chat.service.ts** - Chat and messaging endpoints
- **pdf.service.ts** - PDF upload and management endpoints

All API calls include:
- Automatic token injection
- Request/response interceptors
- Error handling
- Type-safe responses

## Path Aliases

The project uses path aliases for cleaner imports:

```typescript
import { Button } from '@/components/common';
import { useAuthStore } from '@/stores/useAuthStore';
import { API_ENDPOINTS } from '@/constants';
```

Available aliases:
- `@/*` - src directory
- `@/components/*` - components directory
- `@/hooks/*` - hooks directory
- `@/services/*` - services directory
- `@/stores/*` - stores directory
- `@/types/*` - types directory
- `@/utils/*` - utils directory
- `@/constants/*` - constants directory
- `@/assets/*` - assets directory

## TypeScript Configuration

The project uses strict TypeScript settings for better type safety:
- `strict: true`
- `noImplicitAny: true`
- `strictNullChecks: true`
- Path aliases configured
- Type definitions for environment variables

## Styling

### Tailwind CSS
Utility-first CSS framework with custom configuration:
- Custom color palette (primary colors)
- Custom component classes
- Responsive breakpoints
- Dark mode ready (to be implemented)

### Custom Components
Pre-styled component classes available:
- `.btn-primary` - Primary action button
- `.btn-secondary` - Secondary action button
- `.input-field` - Form input field
- `.card` - Content card

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Contributing

1. Follow the existing code structure
2. Use TypeScript for all new components
3. Follow the ESLint and Prettier configurations
4. Write semantic commit messages
5. Test thoroughly before submitting

## License

MIT
