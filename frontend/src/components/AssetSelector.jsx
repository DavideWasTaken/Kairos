
import React, { useState, useEffect, useRef } from 'react';
import { Search } from 'lucide-react';
import { searchAssets } from '../api';

const AssetSelector = ({ onSearch, isLoading, compact = false, initialQuery = 'AAPL', className = '' }) => {
  const [query, setQuery] = useState(initialQuery || 'AAPL');
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [inputError, setInputError] = useState('');
  const wrapperRef = useRef(null);
  const debounceTimeout = useRef(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (typeof initialQuery === 'string' && initialQuery.trim()) {
      setQuery(initialQuery.trim().toUpperCase());
    }
  }, [initialQuery]);

  const submitTicker = (tickerValue) => {
    const clean = (tickerValue || '').trim().toUpperCase();
    if (!clean) return;
    onSearch(clean);
    setShowSuggestions(false);
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fetchSuggestions = async (searchTerm) => {
    const term = (searchTerm || '').trim();
    if (term.length < 2) {
      setSuggestions([]);
      setActiveIndex(-1);
      return;
    }

    const reqId = ++requestIdRef.current;
    setIsSearching(true);
    try {
      const results = await searchAssets(term);
      if (reqId !== requestIdRef.current) return;
      const cleaned = (results || []).filter((r) => r && r.symbol).slice(0, 10);
      setSuggestions(cleaned);
      setActiveIndex(cleaned.length > 0 ? 0 : -1);
      setShowSuggestions(true);
      if (cleaned.length > 0) {
        setInputError('');
      }
    } catch (error) {
      console.error("Failed to search assets", error);
      setSuggestions([]);
      setActiveIndex(-1);
    } finally {
      if (reqId === requestIdRef.current) {
        setIsSearching(false);
      }
    }
  };

  const handleInputChange = (e) => {
    const value = e.target.value;
    setQuery(value);
    setShowSuggestions(true);
    setInputError('');

    if (debounceTimeout.current) {
      clearTimeout(debounceTimeout.current);
    }

    if (value.length > 1) {
      debounceTimeout.current = setTimeout(() => {
        fetchSuggestions(value);
      }, 300); // 300ms debounce
    } else {
      setSuggestions([]);
      setActiveIndex(-1);
      setShowSuggestions(false);
    }
  };

  const handleSelect = (asset, shouldSearch = true) => {
    setQuery(asset.symbol);
    setSuggestions([]);
    setActiveIndex(-1);
    setShowSuggestions(false);
    setInputError('');
    if (shouldSearch) {
      submitTicker(asset.symbol);
    }
  };

  const pickBestSuggestion = (term, list) => {
    const t = term.trim().toUpperCase();
    if (!t || !Array.isArray(list) || list.length === 0) return null;
    const exact = list.find((s) => (s.symbol || '').toUpperCase() === t);
    if (exact) return exact;
    const symbolPrefix = list.find((s) => (s.symbol || '').toUpperCase().startsWith(t));
    if (symbolPrefix) return symbolPrefix;
    const namePrefix = list.find((s) => (s.name || '').toUpperCase().startsWith(t));
    if (namePrefix) return namePrefix;
    return list[0];
  };

  const isTickerLike = (value) => /^[A-Za-z0-9.^=-]{1,15}$/.test((value || '').trim());

  const handleSubmit = async (e) => {
    e.preventDefault();
    setInputError('');

    const term = query.trim();
    if (!term) return;

    if (showSuggestions && suggestions.length > 0) {
      const idx = activeIndex >= 0 ? activeIndex : 0;
      handleSelect(suggestions[idx], true);
      return;
    }

    // If user presses Analyze before debounce results are ready, force a lookup now.
    setIsSearching(true);
    try {
      const results = await searchAssets(term);
      const cleaned = (results || []).filter((r) => r && r.symbol).slice(0, 10);
      setSuggestions(cleaned);
      setActiveIndex(cleaned.length > 0 ? 0 : -1);
      setShowSuggestions(true);

      const best = pickBestSuggestion(term, cleaned);
      if (best) {
        handleSelect(best, true);
      } else {
        if (isTickerLike(term)) {
          submitTicker(term);
        } else {
          setInputError('Ticker not found. Select one from suggestions.');
        }
      }
    } catch {
      setInputError('Lookup failed. Try again.');
    } finally {
      setIsSearching(false);
    }
  };

  const handleKeyDown = (e) => {
    if (!showSuggestions || suggestions.length === 0) {
      if (e.key === 'Enter') handleSubmit(e);
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % suggestions.length);
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => (prev <= 0 ? suggestions.length - 1 : prev - 1));
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const idx = activeIndex >= 0 ? activeIndex : 0;
      handleSelect(suggestions[idx], true);
      return;
    }
    if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  return (
    <div
      className={`${compact ? 'w-full max-w-3xl mx-auto p-0' : 'w-full max-w-md mx-auto p-4'} relative ${className}`}
      ref={wrapperRef}
    >
      <form onSubmit={handleSubmit} className="flex gap-2 relative">
        <div className="relative flex-1">
          <input
            type="text"
            aria-label="Asset name or ticker"
            maxLength={100}
            value={query}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              if (query && query.trim().length > 1) {
                fetchSuggestions(query);
              }
            }}
            placeholder="Search by name or ticker (e.g. Apple, AAPL, BTC-USD)"
            className={`w-full px-4 ${compact ? 'py-2.5' : 'py-2'} bg-secondary text-foreground rounded-lg border border-input focus:outline-none focus:ring-2 focus:ring-ring`}
            disabled={isLoading}
          />

          {showSuggestions && (
            <div className="absolute z-10 w-full mt-1 bg-popover border border-border rounded-lg shadow-lg max-h-60 overflow-y-auto">
              {isSearching && (
                <div className="px-4 py-3 text-sm text-muted-foreground">Searching tickers...</div>
              )}

              {!isSearching && suggestions.map((asset, idx) => (
                <button
                  key={`${asset.symbol}-${idx}`}
                  type="button"
                  className={`w-full text-left px-4 py-2 cursor-pointer flex justify-between items-center ${
                    idx === activeIndex ? 'bg-muted' : 'hover:bg-muted'
                  }`}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={() => handleSelect(asset, true)}
                >
                  <span className="font-bold">{asset.symbol}</span>
                  <div className="flex flex-col items-end overflow-hidden max-w-[60%]">
                    <span className="text-sm text-muted-foreground truncate">{asset.name}</span>
                    <span className="text-xs text-muted-foreground/50">{asset.exchange} - {asset.type}</span>
                  </div>
                </button>
              ))}

              {!isSearching && suggestions.length === 0 && query.trim().length > 1 && (
                <div className="px-4 py-3 text-sm text-muted-foreground">
                  No ticker suggestions found. You can still press Analyze to try this symbol.
                </div>
              )}
            </div>
          )}
        </div>

        <button
          type="submit"
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 flex items-center gap-2 disabled:opacity-50"
          disabled={isLoading || isSearching}
        >
          {isLoading || isSearching ? (
            <span className="animate-spin h-5 w-5 border-2 border-b-transparent rounded-full" />
          ) : (
            <Search className="h-5 w-5" />
          )}
          Analyze
        </button>
      </form>
      {inputError && (
        <div className="mt-2 text-xs text-red-400 text-center">{inputError}</div>
      )}
      {!compact && (
        <div className="mt-2 text-xs text-muted-foreground text-center">
          Tip: start typing a asset name and pick a suggested ticker.
        </div>
      )}
    </div>
  );
};
export default AssetSelector;
