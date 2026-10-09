// Every brand decision lives here. Set VITE_BRAND=neutral to remove client marks in minutes.
const neutral = import.meta.env.VITE_BRAND === 'neutral'

export const brand = {
  client: neutral ? 'Global Business Services' : 'Mastercard',
  product: 'CLEAR',
  expansion: 'Coding, Ledger, Exceptions, Approvals, Reconciliation',
  unit: 'GBSC Finance · Accounts Payable',
  logo: neutral ? null : '/brand/mastercard-symbol.svg',
  wordmark: neutral ? null : '/brand/mastercard-logo.svg',
  disclaimer: 'Demonstration on synthetic data · built by Ciklum',
  colors: {
    ink: '#1B1D21',
    paper: '#F6F7F9',
    panel: '#FFFFFF',
    line: '#E4E6EA',
    muted: '#6B7079',
    red: '#EB001B',
    yellow: '#F79E1B',
    orange: '#FF5F00',
    green: '#16794C',
    blue: '#2F5F8F',
  },
  font: "'Geist', 'Helvetica Neue', Arial, sans-serif",
}

export const chartColors = ['#1B1D21', '#FF5F00', '#2F5F8F', '#A3A7AE', '#F79E1B', '#16794C']
