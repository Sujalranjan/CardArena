import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { LandingPage } from '../pages/LandingPage';
import { describe, it, expect } from 'vitest';

describe('LandingPage', () => {
  it('renders landing page with platform title and server-authoritative badge', () => {
    render(
      <BrowserRouter>
        <LandingPage />
      </BrowserRouter>
    );

    expect(screen.getByText(/Next-Gen Multiplayer/i)).toBeDefined();
    expect(screen.getByText(/Server-Authoritative Architecture/i)).toBeDefined();
    expect(screen.getByRole('link', { name: /Launch Lobby & Play/i })).toBeDefined();
  });
});
