// Every brand decision lives here. Set VITE_BRAND=neutral to remove client marks in minutes.
const neutral = import.meta.env.VITE_BRAND === 'neutral'

export const brand = {
  client: neutral ? 'Global Business Services' : 'Mastercard',
  product: 'Non-PO Invoice Agent',
  unit: 'GBSC Finance · Accounts Payable',
  logo: neutral ? null : '/brand/mastercard-symbol.svg',
  wordmark: neutral ? null : '/brand/mastercard-logo.svg',
  disclaimer: 'Demonstration on synthetic data · built by Ciklum',
  colors: {
    ink: '#141413',
    paper: '#F3F0EE',
    panel: '#FFFFFF',
    line: '#DCD6D1',
    muted: '#5F5A55',
    red: '#EB001B',
    yellow: '#F79E1B',
    orange: '#FF5F00',
    green: '#1A7F4B',
    blue: '#2C5D8A',
  },
  font: "'Figtree', 'Helvetica Neue', Arial, sans-serif",
}

export const chartColors = ['#141413', '#FF5F00', '#2C5D8A', '#9C8F84', '#F79E1B', '#1A7F4B']
