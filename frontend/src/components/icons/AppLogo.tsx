export function AppLogo() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 0' }}>
      <img src="/logo.png" alt="Strava AI Boost" style={{ width: 32, height: 32, borderRadius: 6 }} />
      <div style={{ lineHeight: 1.2 }}>
        <div style={{ fontWeight: 700, fontSize: 16, color: '#000716' }}>AI Boost</div>
        <div style={{ fontSize: 11, color: '#5f6b7a', letterSpacing: '0.5px' }}>for Strava</div>
      </div>
    </div>
  );
}
