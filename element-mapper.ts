/**
 * element-mapper.ts: This module provides functionality to extract a comprehensive JSON representation
 * of all UI elements on a webpage using Playwright's CDP capabilities. It captures DOM elements,
 * accessibility information, and multiple selector strategies for robust element identification.
 * It fully supports shadow DOM and iframe elements.
 *
 * Enhanced with CDP Session Strategy and Accessibility Tree Strategy for self-healing test automation.
 */

import { Locator, Page } from '@playwright/test';
import { run } from 'node:test';
import { ClientFunction, Selector } from 'testcafe';
import { GoogleADKClient, GoogleADKHealingRequest } from '../communication/google-adk-client';
import { VisualHealingService } from './visualHealingService';
import logger from '../utils/logger';
import { JSONLLogger } from '../utils/jsonl-logger';
import { t as TestController} from 'testcafe';

const adkClient = new GoogleADKClient();
const jsonlLogger = JSONLLogger.getInstance();

/**
 * Generates properly formatted Playwright locator strings with single quotes and no escape characters.
 * This ensures consistency with the JSON repair patterns in google-adk-client.ts
 * 
 * Comprehensive coverage includes:
 * - getByRole: with name, exact, pressed, expanded, checked, includeHidden options
 * - getByText: with exact and ignoreCase options
 * - getByLabel: with exact option
 * - getByPlaceholder: with exact option
 * - getByAltText: with exact option
 * - getByTitle: with exact option
 * - getByTestId: basic pattern
 * - locator: basic, with hasText, with has options
 * - frameLocator: basic pattern
 * - nth, first, last: chaining methods
 * - filter: with hasText and has options
 */
function generatePlaywrightLocatorString(type: string, options: Record<string, any> = {}): string {
  switch (type) {
    case 'getByRole':
      const { role, name, exact, pressed, expanded, checked, includeHidden } = options;
      if (!role) return '';
      
      let roleOptions: string[] = [];
      if (name) roleOptions.push(`name: '${name}'`);
      if (exact !== undefined) roleOptions.push(`exact: ${exact}`);
      if (pressed !== undefined) roleOptions.push(`pressed: ${pressed}`);
      if (expanded !== undefined) roleOptions.push(`expanded: ${expanded}`);
      if (checked !== undefined) roleOptions.push(`checked: ${checked}`);
      if (includeHidden !== undefined) roleOptions.push(`includeHidden: ${includeHidden}`);
      
      if (roleOptions.length > 0) {
        return `getByRole('${role}', { ${roleOptions.join(', ')} })`;
      }
      return `getByRole('${role}')`;
      
    case 'getByText':
      const { text, textExact, ignoreCase } = options;
      if (!text) return '';
      
      let textOptions: string[] = [];
      if (textExact !== undefined) textOptions.push(`exact: ${textExact}`);
      if (ignoreCase !== undefined) textOptions.push(`ignoreCase: ${ignoreCase}`);
      
      if (textOptions.length > 0) {
        return `getByText('${text}', { ${textOptions.join(', ')} })`;
      }
      return `getByText('${text}')`;
      
    case 'getByLabel':
      const { label, labelExact } = options;
      if (!label) return '';
      
      if (labelExact !== undefined) {
        return `getByLabel('${label}', { exact: ${labelExact} })`;
      }
      return `getByLabel('${label}')`;
      
    case 'getByPlaceholder':
      const { placeholder, placeholderExact } = options;
      if (!placeholder) return '';
      
      if (placeholderExact !== undefined) {
        return `getByPlaceholder('${placeholder}', { exact: ${placeholderExact} })`;
      }
      return `getByPlaceholder('${placeholder}')`;
      
    case 'getByAltText':
      const { altText, altTextExact } = options;
      if (!altText) return '';
      
      if (altTextExact !== undefined) {
        return `getByAltText('${altText}', { exact: ${altTextExact} })`;
      }
      return `getByAltText('${altText}')`;
      
    case 'getByTitle':
      const { title, titleExact } = options;
      if (!title) return '';
      
      if (titleExact !== undefined) {
        return `getByTitle('${title}', { exact: ${titleExact} })`;
      }
      return `getByTitle('${title}')`;
      
    case 'getByTestId':
      const { testId } = options;
      if (!testId) return '';
      return `getByTestId('${testId}')`;
      
    case 'locator':
      const { selector, hasText, has } = options;
      if (!selector) return '';
      
      let locatorOptions: string[] = [];
      if (hasText) locatorOptions.push(`hasText: '${hasText}'`);
      if (has) locatorOptions.push(`has: '${has}'`);
      
      if (locatorOptions.length > 0) {
        return `locator('${selector}', { ${locatorOptions.join(', ')} })`;
      }
      return `locator('${selector}')`;
      
    case 'frameLocator':
      const { frameSelector } = options;
      if (!frameSelector) return '';
      return `frameLocator('${frameSelector}')`;
      
    case 'nth':
      const { baseSelector, index } = options;
      if (!baseSelector || index === undefined) return '';
      return `locator('${baseSelector}').nth(${index})`;
      
    case 'first':
      const { firstSelector } = options;
      if (!firstSelector) return '';
      return `locator('${firstSelector}').first()`;
      
    case 'last':
      const { lastSelector } = options;
      if (!lastSelector) return '';
      return `locator('${lastSelector}').last()`;
      
    case 'filter':
      const { filterSelector, filterOptions } = options;
      if (!filterSelector) return '';
      
      let filterOpts: string[] = [];
      if (filterOptions?.hasText) filterOpts.push(`hasText: '${filterOptions.hasText}'`);
      if (filterOptions?.has) filterOpts.push(`has: '${filterOptions.has}'`);
      
      if (filterOpts.length > 0) {
        return `locator('${filterSelector}').filter({ ${filterOpts.join(', ')} })`;
      }
      return `locator('${filterSelector}').filter({})`;
      
    default:
      return '';
  }
}
/**
 * Interface for interaction history data
 */
export interface InteractionHistoryData {
  selector: string;
  selectorType: string;
  timestamp: Date;
  success: boolean;
  gherkinStep: string;
  framework: 'playwright' | 'testcafe';
  metadata?: Record<string, any>;
}

/**
 * Interface for historical execution data
 */
export interface HistoricalExecutionData {
  selector: string;
  selectorType: string;
  timestamp: Date;
  success: boolean;
  gherkinStep: string;
  framework: 'playwright' | 'testcafe';
  pageUrl: string;
  testName: string;
  confidence: number;
}

/**
 * Interface for predicted selector
 */
export interface PredictedSelector {
  selector: string;
  type: string;
  confidence: number;
  reasoning: string;
}

/**
 * Interface for visual analysis result
 */
export interface VisualAnalysisResult {
  targetElement?: {
    x: number;
    y: number;
    width: number;
    height: number;
    text?: string;
    attributes?: Record<string, string>;
  };
  confidence: number;
  differences: Array<{
    type: 'added' | 'removed' | 'modified';
    element: any;
    confidence: number;
  }>;
}

/**
 * Interface for visual selector
 */
export interface VisualSelector {
  selector: string;
  type: string;
  confidence: number;
  coordinates: { x: number; y: number; width: number; height: number };
}

/**
 * Interface for test result
 */
export interface TestResult {
  success: boolean;
  count?: number;
  error?: string;
}

/**
 * Interface for the result of a self-healing attempt.
 */
export interface HealedLocatorResult {
  success: boolean;
  originalLocator: string;
  originalLocatorType: string; // e.g., 'xpath', 'css', 'getByRole', 'getByText'
  healedLocator?: string; // The selector string of the healed locator
  healedLocatorType?: LocatorStrategy['type']; // The type of the healed locator strategy
  strategyApplied?: string; // Describes how the healing was achieved (e.g., "candidate_locator_getByRole", "property_similarity_match")
  confidence?: number; // Overall confidence in the healed locator (0-1)
  elementDetails?: Partial<ComprehensiveElementData>; // Key details of the healed element
  message?: string; // A message describing the outcome
}

/**
 * Interface for properties inferred from a failing locator, used for similarity matching.
 */
interface InferredElementProperties {
  tagName?: string;
  id?: string;
  text?: string;
  textPattern?: RegExp; // For more flexible text matching
  attributes?: Record<string, string | RegExp>; // e.g., class, data-testid
  role?: string;
  name?: string; // Accessible name
  // Consider adding parentHierarchyPattern if structural matching becomes critical
}


/**
 * Attempts to find a "healed" locator for a given failing locator,
 * using a pre-computed ComprehensiveDOMAnalysis of the current page state.
 *
 * @param page Playwright Page object for verifying locators.
 * @param domAnalysis The comprehensive analysis of the current DOM.
 * @param failingLocator The original locator string that failed (e.g., "getByRole('button', { name: 'Submit' })" or "//button[@id='submit']").
 * @param originalLocatorType The type of the original failing locator (e.g., 'getByRole', 'xpath', 'css').
 * @returns A Promise resolving to a HealedLocatorResult object.
 */
export async function findHealedLocatorUsingDomAnalysis(
  page: Page,
  domAnalysis: ComprehensiveDOMAnalysis,
  failingLocator: string,
  originalLocatorType: string
): Promise<HealedLocatorResult> {
  

  // --- Strategy 1: Iterate through all elements and their pre-generated candidate locators ---
  // This is the most reliable strategy as candidates are generated with context.
  for (const elementData of domAnalysis.elements) {
    if (!elementData.visual.isVisible && !domAnalysis.extractionMetadata.options?.includeHidden) {
      continue; // Skip non-visible elements if not explicitly included
    }
    for (const candidate of elementData.locatorCandidates) {
      try {
        let locatedElement: Locator | undefined;
        let verificationSelector = candidate.selector; // Default selector to verify

        // Construct Playwright locator based on candidate type
        switch (candidate.type) {
          case 'id':
          case 'data-testid':
          case 'css':
          case 'xpath':
          case 'aria-label': // Assuming aria-label candidate selector is a valid CSS/XPath
            locatedElement = page.locator(candidate.selector);
            break;
          case 'getByRole':
            // Use the actual role and name from elementData for higher accuracy
            const role = elementData.accessibility.role;
            const name = elementData.accessibility.name;
            if (role) {
              locatedElement = name ? page.getByRole(role as any, { name, exact: true }) : page.getByRole(role as any);
              if (name && (!locatedElement || await locatedElement.count() === 0 || !await locatedElement.first().isVisible())) {
                locatedElement = page.getByRole(role as any, { name }); // Try non-exact name
              }
              if (!locatedElement || await locatedElement.count() === 0 || !await locatedElement.first().isVisible()) {
                locatedElement = page.getByRole(role as any); // Try role only
              }
              // For reporting, we might still use the original candidate.selector or a more descriptive one
              verificationSelector = generatePlaywrightLocatorString('getByRole', { role, name });
            }
            break;
          case 'getByText':
            // Use the actual textContent or accessible name from elementData
            const text = elementData.textContent || elementData.accessibility.name;
            if (text) {
              locatedElement = page.getByText(text, { exact: true });
              if (!locatedElement || await locatedElement.count() === 0 || !await locatedElement.first().isVisible()) {
                locatedElement = page.getByText(text); // Try non-exact text
              }
              verificationSelector = generatePlaywrightLocatorString('getByText', { text });
            }
            break;
          default:
            logger.warn(`[SelfHealing] Unknown candidate locator type: ${candidate.type}`);
            continue;
        }

        if (locatedElement && await locatedElement.count() > 0) {
          const firstMatch = locatedElement.first();
          if (await firstMatch.isVisible()) {
        
            return {
              success: true,
              originalLocator: failingLocator,
              originalLocatorType,
              healedLocator: verificationSelector, // Use the potentially more specific selector
              healedLocatorType: candidate.type,
              strategyApplied: `candidate_locator_${candidate.type}`,
              confidence: candidate.confidence,
              elementDetails: { // Populate with key details from elementData
                tagName: elementData.tagName,
                attributes: elementData.attributes,
                textContent: elementData.textContent,
                accessibility: elementData.accessibility,
              },
              message: 'Successfully healed using a candidate locator from DOM analysis.',
            };
          }
        }
      } catch (error) {
        // Log quietly or with a debug flag, as many candidates might fail
        // logger.debug(`[SelfHealing] Candidate ${candidate.selector} for ${elementData.tagName} failed verification: ${error instanceof Error ? error.message.split('\n')[0] : String(error).split('\n')[0]}`);
      }
    }
  }
  

  // --- Strategy 2: Property-Based Similarity Matching ---
  // This is a fallback if direct candidate locators fail.
  if (domAnalysis.elements.length > 0) {

    let bestMatch: { element: ComprehensiveElementData; score: number } | undefined;
    const inferredProperties = inferPropertiesFromFailedLocator(failingLocator, originalLocatorType);
    const MIN_SIMILARITY_THRESHOLD_CONSIDER = 0.50; // Lower threshold to consider an element
    const MIN_SIMILARITY_THRESHOLD_ACCEPT = 0.65;  // Higher threshold to accept an element

    for (const currentElementData of domAnalysis.elements) {
      if (!currentElementData.visual.isVisible && !domAnalysis.extractionMetadata.options?.includeHidden) {
        continue; // Skip non-visible elements
      }
      const score = calculateSimilarityScore(inferredProperties, currentElementData, domAnalysis.extractionMetadata.options);
      if (score >= MIN_SIMILARITY_THRESHOLD_CONSIDER) {
        if (!bestMatch || score > bestMatch.score) {
          bestMatch = { element: currentElementData, score };
        }
      }
    }

    if (bestMatch && bestMatch.score >= MIN_SIMILARITY_THRESHOLD_ACCEPT) {


      // Now, try to use the *best candidate locator of the matched element*
      // The locatorCandidates are already sorted by confidence in extractComprehensiveDOMData
      for (const candidate of bestMatch.element.locatorCandidates) {
        try {
          let locatedElement: Locator | undefined;
          let verificationSelector = candidate.selector;

          switch (candidate.type) {
            case 'id': case 'data-testid': case 'css': case 'xpath': case 'aria-label':
              locatedElement = page.locator(candidate.selector);
              break;
            case 'getByRole':
              const role = bestMatch.element.accessibility.role;
              const name = bestMatch.element.accessibility.name;
              if (role) {
                locatedElement = name ? page.getByRole(role as any, { name, exact: true }) : page.getByRole(role as any);
                if (name && (!locatedElement || await locatedElement.count() === 0 || !await locatedElement.first().isVisible())) {
                  locatedElement = page.getByRole(role as any, { name });
                }
                if (!locatedElement || await locatedElement.count() === 0 || !await locatedElement.first().isVisible()) {
                  locatedElement = page.getByRole(role as any);
                }
                verificationSelector = generatePlaywrightLocatorString('getByRole', { role, name });
              }
              break;
            case 'getByText':
              const text = bestMatch.element.textContent || bestMatch.element.accessibility.name;
              if (text) {
                locatedElement = page.getByText(text, { exact: true });
                if (!locatedElement || await locatedElement.count() === 0 || !await locatedElement.first().isVisible()) {
                  locatedElement = page.getByText(text);
                }
                verificationSelector = generatePlaywrightLocatorString('getByText', { text });
              }
              break;
          }

          if (locatedElement && await locatedElement.count() > 0 && await locatedElement.first().isVisible()) {

            return {
              success: true,
              originalLocator: failingLocator,
              originalLocatorType,
              healedLocator: verificationSelector,
              healedLocatorType: candidate.type,
              strategyApplied: `property_similarity_match (score: ${bestMatch.score.toFixed(2)})`,
              confidence: parseFloat((candidate.confidence * bestMatch.score).toFixed(2)), // Combine confidences
              elementDetails: {
                tagName: bestMatch.element.tagName,
                attributes: bestMatch.element.attributes,
                textContent: bestMatch.element.textContent,
                accessibility: bestMatch.element.accessibility,
              },
              message: 'Successfully healed using property-based similarity and verified with a candidate locator.',
            };
          }
        } catch (verifyError) {
          logger.debug(`[SelfHealing] Verification of property-based match candidate ${candidate.selector} for ${bestMatch.element.tagName} failed: ${verifyError instanceof Error ? verifyError.message.split('\n')[0] : String(verifyError).split('\n')[0]}`);
        }
      }
      logger.warn(`[SelfHealing] Property similarity found a good match (score: ${bestMatch.score.toFixed(2)}), but none of its candidate locators could be verified.`);
    }
  }


  return {
    success: false,
    originalLocator: failingLocator,
    originalLocatorType,
    message: 'Self-healing failed. No suitable candidate locator or similar element found in the DOM analysis.',
  };
}

/**
 * Infers expected properties from a failing locator string.
 * This is a simplified parser. For production, consider a more robust solution
 * or storing baseline element data.
 */
function inferPropertiesFromFailedLocator(locator: string, type: string): InferredElementProperties {
  const props: InferredElementProperties = {};
  const normalizedType = type.toLowerCase();

  if (normalizedType.includes('xpath')) {
    const tagMatch = locator.match(/^\/\/(?:[\w-]+:)?([\w*-]+)/);
    if (tagMatch && tagMatch[1] !== '*') props.tagName = tagMatch[1].toLowerCase();

    const idMatch = locator.match(/@id=['"]([^'"]+)['"]/);
    if (idMatch) props.id = idMatch[1];

    const textMatch = locator.match(/(?:text\(\)=['"]([^'"]+)['"]|contains\((?:text\(\)|normalize-space\(text\(\)|normalize-space\(\.\)|\.),\s*['"]([^'"]+)['"]\))/);
    if (textMatch) props.text = textMatch[1] || textMatch[2];

    const roleMatch = locator.match(/@role=['"]([^'"]+)['"]/);
    if (roleMatch) props.role = roleMatch[1];

    const classMatch = locator.match(/contains\(@class,\s*['"]([^'"]+)['"]\)|@class=['"]([^'"]+)['"]/);
    if (classMatch) props.attributes = { ...props.attributes, class: classMatch[1] || classMatch[2] };

    // data-testid
    const testIdMatch = locator.match(/@data-testid=['"]([^'"]+)['"]/);
    if (testIdMatch) props.attributes = { ...props.attributes, 'data-testid': testIdMatch[1] };

  } else if (normalizedType.includes('css')) {
    // Basic CSS parsing
    const idMatch = locator.match(/#([a-zA-Z0-9_-]+)/);
    if (idMatch) props.id = idMatch[1];

    const classMatch = locator.match(/\.([a-zA-Z0-9_-]+)/); // Matches the first class
    if (classMatch) props.attributes = { ...props.attributes, class: classMatch[1] };

    const tagMatch = locator.match(/^([a-zA-Z0-9_-]+)(?:[.#\[]|$)/);
    if (tagMatch && !props.id && !props.attributes?.class) props.tagName = tagMatch[1].toLowerCase();

    const attrMatches = locator.matchAll(/\[([a-zA-Z0-9_-]+)(?:(?:(\*|\^|\$|~|\|)?=)(?:['"]?([^'"\]]+)['"]?))?\]/g);
    for (const match of attrMatches) {
      if (!props.attributes) props.attributes = {};
      props.attributes[match[1]] = match[4] || new RegExp(".*"); // If only attribute name, match any value
    }
  } else if (normalizedType.includes('getbyrole')) {
    const roleMatch = locator.match(/getByRole\(['"]([^'"]+)['"]/);
    if (roleMatch) props.role = roleMatch[1];
    const nameMatch = locator.match(/name:\s*['"]([^'"]+)['"]/);
    if (nameMatch) props.name = nameMatch[1];
  } else if (normalizedType.includes('getbytext')) {
    const textMatch = locator.match(/getByText\(['"]([^'"]+)['"]/);
    if (textMatch) props.text = textMatch[1];
  } else if (normalizedType.includes('getbylabel')) {
    const labelMatch = locator.match(/getByLabel\(['"]([^'"]+)['"]/);
    if (labelMatch) props.attributes = { ...props.attributes, 'aria-label': labelMatch[1] }; // or props.name
  } else if (normalizedType.includes('getbytestid')) {
    const testIdMatch = locator.match(/getByTestId\(['"]([^'"]+)['"]/);
    if (testIdMatch) props.attributes = { ...props.attributes, 'data-testid': testIdMatch[1] };
  }
  // console.debug(`[SelfHealing] Inferred properties from '${type} ${locator}':`, JSON.stringify(props));
  return props;
}

/**
 * Calculates a similarity score between inferred properties and a current element.
 */
function calculateSimilarityScore(
  inferredProps: InferredElementProperties,
  currentElement: ComprehensiveElementData,
  domAnalysisOptions?: ExtractUIElementsOptions
): number {
  let score = 0;
  let weightSum = 0;

  // Define weights for different properties
  const weights = {
    id: 0.30,
    name: 0.25, // Accessible Name
    role: 0.15,
    text: 0.15,
    attributes: 0.10, // For data-testid or specific classes
    tagName: 0.05,
  };

  // ID matching
  if (inferredProps.id) {
    weightSum += weights.id;
    if (currentElement.attributes.id === inferredProps.id) {
      score += weights.id;
    } else if (currentElement.attributes.id?.includes(inferredProps.id) || inferredProps.id.includes(currentElement.attributes.id || '')) {
      score += weights.id * 0.6; // Partial match
    }
  }

  // Accessible Name matching
  if (inferredProps.name) {
    weightSum += weights.name;
    if (currentElement.accessibility.name) {
      const sim = stringSimilarity(inferredProps.name, currentElement.accessibility.name, domAnalysisOptions?.debugMode);
      if (sim > 0.7) score += weights.name * sim;
    }
  }

  // Role matching
  if (inferredProps.role) {
    weightSum += weights.role;
    if (currentElement.accessibility.role === inferredProps.role) {
      score += weights.role;
    }
  }

  // Text content matching (use accessible name if text is not directly available or less reliable)
  if (inferredProps.text) {
    weightSum += weights.text;
    const textToCompare = currentElement.textContent || currentElement.accessibility.name;
    if (textToCompare) {
      const sim = stringSimilarity(inferredProps.text, textToCompare, domAnalysisOptions?.debugMode);
      if (sim > 0.6) score += weights.text * sim; // Slightly lower threshold for text
    }
  }

  // Specific attribute matching (e.g., data-testid, class)
  if (inferredProps.attributes) {
    weightSum += weights.attributes;
    let attributeMatchScore = 0;
    let consideredAttributes = 0;
    for (const [key, value] of Object.entries(inferredProps.attributes)) {
      if (currentElement.attributes[key]) {
        consideredAttributes++;
        if (value instanceof RegExp) {
          if (value.test(currentElement.attributes[key])) attributeMatchScore += 1;
        } else if (currentElement.attributes[key] === value) {
          attributeMatchScore += 1;
        } else if (currentElement.attributes[key].includes(value as string)) {
          attributeMatchScore += 0.6; // Partial match for string values
        }
      }
    }
    if (consideredAttributes > 0) {
      score += weights.attributes * (attributeMatchScore / consideredAttributes);
    }
  }

  // Tag name matching (lower weight)
  if (inferredProps.tagName) {
    weightSum += weights.tagName;
    if (currentElement.tagName.toLowerCase() === inferredProps.tagName.toLowerCase()) {
      score += weights.tagName;
    }
  }

  // Normalize score
  return weightSum > 0 ? Math.min(score / weightSum, 1.0) : 0;
}

/**
 * Calculates string similarity using Levenshtein distance.
 * Returns a score between 0 (no similarity) and 1 (exact match).
 */
function stringSimilarity(s1: string, s2: string, debugMode = false): number {
  if (s1 === s2) return 1.0;
  if (!s1 || !s2) return 0.0;

  let longer = s1;
  let shorter = s2;
  if (s1.length < s2.length) {
    longer = s2;
    shorter = s1;
  }
  const longerLength = longer.length;
  if (longerLength === 0) {
    return 1.0;
  }
  const distance = editDistance(longer.toLowerCase(), shorter.toLowerCase());
  const similarity = (longerLength - distance) / parseFloat(longerLength.toString());

  // if (debugMode && similarity < 0.7 && similarity > 0.3) {
  //   console.debug(`[StringSimilarity] Compared: "${s1}" vs "${s2}" | Distance: ${distance} | Similarity: ${similarity.toFixed(2)}`);
  // }
  return similarity;
}

/**
 * Calculates the Levenshtein edit distance between two strings.
 */
function editDistance(s1: string, s2: string): number {
  const costs: number[] = [];
  for (let j = 0; j <= s2.length; j++) {
    costs[j] = j;
  }
  for (let i = 1; i <= s1.length; i++) {
    costs[0] = i;
    let nw = i - 1;
    for (let j = 1; j <= s2.length; j++) {
      const cj = Math.min(
        1 + Math.min(costs[j], costs[j - 1]),
        s1.charAt(i - 1) === s2.charAt(j - 1) ? nw : nw + 1
      );
      nw = costs[j];
      costs[j] = cj;
    }
  }
  return costs[s2.length];
}

/**
 * Interface for CDP DOM node information
 */
interface CDPDOMNode {
  nodeId: number;
  nodeType: number;
  nodeName: string;
  localName?: string;
  nodeValue?: string;
  attributes?: string[];
  children?: CDPDOMNode[];
  shadowRoots?: CDPDOMNode[];
  frameId?: string;
  parentId?: number; // Reference to parent node
  depth?: number; // Depth in DOM tree
  contentDocument?: CDPDOMNode; // For iframe document nodes
  isDeepTraversed?: boolean; // Flag to indicate deep traversal
}

/**
 * Interface for accessibility tree node
 */
interface AccessibilityTreeNode {
  nodeId: string;
  role?: string;
  name?: string;
  description?: string;
  value?: string;
  properties?: Record<string, any>;
  children?: AccessibilityTreeNode[];
  domNodeId?: number;
}

/**
 * Interface for comprehensive accessibility data based on WAI-ARIA 1.2
 */
interface ComprehensiveAccessibilityData {
  // Basic accessibility properties
  role?: string;
  name?: string;
  description?: string;
  
  // ARIA labels and descriptions
  ariaLabel?: string;
  ariaLabelledBy?: string;
  ariaDescribedBy?: string;
  
  // ARIA states (Widget Attributes)
  ariaExpanded?: boolean;
  ariaSelected?: boolean;
  ariaChecked?: boolean;
  ariaDisabled?: boolean;
  ariaHidden?: boolean;
  ariaPressed?: boolean;
  ariaCurrent?: string;
  ariaInvalid?: string;
  ariaRequired?: boolean;
  ariaReadOnly?: boolean;
  ariaMultiLine?: boolean;
  ariaMultiSelectable?: boolean;
  ariaOrientation?: string;
  ariaSort?: string;
  ariaGrabbed?: string;
  ariaDropeffect?: string;
  
  // ARIA properties (Relationship Attributes)
  ariaActivedescendant?: string;
  ariaControls?: string;
  ariaOwns?: string;
  ariaFlowto?: string;
  
  // Live Region Attributes
  ariaLive?: string;
  ariaRelevant?: string;
  ariaAtomic?: boolean;
  ariaBusy?: boolean;
  
  // Window Attributes
  ariaModal?: boolean;
  ariaHaspopup?: string;
  
  // Range Attributes
  ariaLevel?: number;
  ariaPosinset?: number;
  ariaSetsize?: number;
  ariaValueMin?: number;
  ariaValueMax?: number;
  ariaValueNow?: number;
  ariaValueText?: string;
  
  // Table Attributes
  ariaColindex?: number;
  ariaColspan?: number;
  ariaRowindex?: number;
  ariaRowspan?: number;
  ariaColcount?: number;
  ariaRowcount?: number;
  
  // Tab index and keyboard navigation
  tabIndex?: number;
  tabStop?: boolean;
  
  // Semantic information
  semanticLabel?: string;
  semanticRole?: string;
  
  // Live region information
  liveRegion?: LiveRegionInfo;
  
  // Form control information
  formControl?: FormControlInfo;
  
  // Landmark information
  landmark?: LandmarkInfo;
  
  // Widget information
  widget?: WidgetInfo;
  
  // Relationship information
  relationships?: RelationshipInfo;
  
  // All ARIA attributes for comprehensive analysis
  ariaAttributes?: Record<string, string>;
  
  // Accessibility compliance
  isAccessible?: boolean;
  accessibilityIssues?: string[];
  
  // Focus management
  focusable?: boolean;
  focusVisible?: boolean;
  
  // Screen reader support
  screenReaderText?: string;
  
  // Keyboard navigation support
  keyboardNavigation?: KeyboardNavigationInfo;
}

/**
 * Interface for live region information
 */
interface LiveRegionInfo {
  live: string;
  relevant: string;
  atomic: boolean;
  busy: boolean;
}

/**
 * Interface for form control information
 */
interface FormControlInfo {
  required: boolean;
  invalid?: string;
  readOnly: boolean;
  multiLine: boolean;
  multiSelectable: boolean;
  orientation?: string;
  valueMin?: number;
  valueMax?: number;
  valueNow?: number;
  valueText?: string;
}

/**
 * Interface for landmark information
 */
interface LandmarkInfo {
  role?: string;
  label?: string;
  labelledBy?: string;
  describedBy?: string;
  description?: string;
}

/**
 * Interface for widget information
 */
interface WidgetInfo {
  expanded: boolean;
  selected: boolean;
  checked: boolean;
  pressed: boolean;
  current?: string;
  hasPopup?: string;
  modal: boolean;
  sort?: string;
  grabbed?: string;
  dropeffect?: string;
}

/**
 * Interface for relationship information
 */
interface RelationshipInfo {
  activeDescendant?: string;
  controls?: string;
  owns?: string;
  flowTo?: string;
  describedBy?: string;
  labelledBy?: string;
}

/**
 * Interface for keyboard navigation information
 */
interface KeyboardNavigationInfo {
  tabbable: boolean;
  enterKey: boolean;
  spaceKey: boolean;
  arrowKeys: boolean;
}

/**
 * Interface for strategy extraction results
 */
export interface StrategyExtractionResult {
  cdpNodes: Record<string, CDPDOMNode>;
  accessibilityNodes: Record<string, AccessibilityTreeNode>;
  extractionTime: number;
  statistics: {
    cdpNodesCount: number;
    accessibilityNodesCount: number;
    elementsWithCDPSelectors: number;
    elementsWithWCAGSelectors: number;
    elementsWithAccessibilitySelectors: number;
  };
}

/**
 * Options for extracting UI elements
 */
export interface ExtractUIElementsOptions {
  includeHidden?: boolean;
  includeIframes?: boolean;
  includeShadowDOM?: boolean;
  maxDepth?: number;
  timeout?: number;
  outputPath?: string;
  selectorStrategies?: string[];
  enableCDPStrategy?: boolean; // Enable CDP session strategy
  enableAccessibilityTreeStrategy?: boolean; // Enable accessibility tree strategy
  generateWCAGCompliantSelectors?: boolean; // Generate WCAG-compliant selectors
  debugMode?: boolean; // Enable debug logging
}

/**
 * Interface for deep interactive element information
 */
export interface DeepInteractiveElement {
  element: CDPDOMNode;
  depth: number;
  path: string[];
  selectors: string[];
  elementType: string;
  attributes: Record<string, string>;
  isVisible: boolean;
  isInteractable: boolean;
}

/**
 * Enhanced interactive element with additional properties
 */
export interface EnhancedInteractiveElement {
  elementType: string;
  nodeId: number;
  depth: number;
  selectors: string[];
  attributes: Record<string, string>;
  isVisible: boolean;
  isInteractable: boolean;
  hasTestAttributes: boolean;
  hasAriaAttributes: boolean;
  path: string[];
}

/**
 * Interface for interactive element analysis results
 */
export interface InteractiveElementAnalysis {
  interactiveelement: EnhancedInteractiveElement[];
  summary: {
    totalElements: number;
    byType: Record<string, number>;
    byDepth: Record<number, number>;
    byRole: Record<string, number>;
    averageDepth: number;
    maxDepth: number;
    elementsWithIds: number;
    elementsWithTestIds: number;
    elementsWithAriaLabels: number;
    elementsWithRoles: number;
  };
  total: number;
}

/**
 * Interface for locator strategy with confidence scoring
 */
export interface LocatorStrategy {
  type: 'id' | 'getByRole' | 'getByText' | 'aria-label' | 'data-testid' | 'css' | 'xpath';
  selector: string;
  confidence: number; // 0-1 confidence score
  isWCAGCompliant: boolean;
  description?: string;
}

/**
 * Interface for framework detection hints
 */
export interface FrameworkHints {
  react?: {
    componentName?: string;
    props?: Record<string, any>;
    hooks?: string[];
  };
  angular?: {
    componentName?: string;
    directives?: string[];
    services?: string[];
  };
  vue?: {
    componentName?: string;
    props?: Record<string, any>;
    directives?: string[];
  };
  materialUI?: {
    componentType?: string;
    variant?: string;
    theme?: string;
  };
  agGrid?: {
    cellType?: string;
    columnId?: string;
    rowIndex?: number;
  };
}

/**
 * Interface for comprehensive element data
 */
export interface ComprehensiveElementData {
  // Basic properties
  tagName: string;
  nodeId: number;
  nodeType: number;
  attributes: Record<string, string>;
  textContent?: string;

  // Accessibility data
  accessibility: ComprehensiveAccessibilityData;

  // Visual properties
  visual: {
    boundingBox?: {
      x: number;
      y: number;
      width: number;
      height: number;
    };
    styles?: Record<string, string>;
    isVisible: boolean;
    isInViewport?: boolean;
    zIndex?: number;
  };

  // Framework detection
  frameworkHints: FrameworkHints;

  // Locator candidates with confidence scoring
  locatorCandidates: LocatorStrategy[];

  // Parent hierarchy
  parentHierarchy: string[];

  // Event handlers
  eventHandlers: string[];

  // Interaction properties
  isInteractable: boolean;
  interactionType?: 'click' | 'input' | 'select' | 'drag' | 'hover' | 'scroll' | 'resize' | 'submit' | 'focus' | 'blur' | 'keydown' | 'keyup' | 'keypress' | 'mouseover' | 'mouseout' | 'touchstart' | 'touchend' | 'touchmove' | 'contextmenu' | 'dblclick' | 'wheel' | 'dragstart' | 'dragend' | 'drop';
}

/**
 * Interface for comprehensive DOM analysis result
 */
export interface ComprehensiveDOMAnalysis {
  pageUrl: string;
  timestamp: string;
  viewport: {
    width: number;
    height: number;
    deviceScaleFactor: number;
  };
  elements: ComprehensiveElementData[];
  statistics: {
    totalElements: number;
    interactiveElements: number;
    elementsWithIds: number;
    elementsWithTestIds: number;
    elementsWithAriaLabels: number;
    frameworkComponents: {
      react: number;
      angular: number;
      vue: number;
      materialUI: number;
      agGrid: number;
    };
    averageConfidenceScore: number;
    wcagCompliantElements: number;
  };
  extractionMetadata: {
    cdpNodesExtracted: number;
    accessibilityNodesExtracted: number;
    extractionTime: number;
    options?: ExtractUIElementsOptions;
    strategies: string[];
  };
}
function isPlaywrightPage(pageOrController: Page | TestController): pageOrController is Page {
  return (pageOrController as Page).context !== undefined;
}
/**
 * CDP Session Strategy: Extract DOM information using Chrome DevTools Protocol
 * Enhanced version with deep traversal and comprehensive element extraction
 * @param {Page} page - Playwright page object
 * @returns {Promise<Record<string, CDPDOMNode>>} - CDP DOM nodes map
 */
export async function extractCDPDOMNodes(page: Page | TestController): Promise<Record<string, CDPDOMNode>> {
  
    const cdpNodes: Record<string, CDPDOMNode> = {};
    const processedNodeIds = new Set<number>();
  try {
    //const cdpSession = await page.context().newCDPSession(page);
    let  root ;
     let cdpSession: any;
    if (isPlaywrightPage(page)) {
      cdpSession = await page.context().newCDPSession(page);
       // Enable DOM domain
    await cdpSession.send('DOM.enable');
    await cdpSession.send('Accessibility.enable');

    // Get the document root with full depth
     root= await cdpSession.send('DOM.getDocument', { depth: -1, pierce: true });

    } else if(isTestCafeController(page)) {
      cdpSession = await (page as TestController).getCurrentCDPSession();
      // Enable required CDP domains
      await cdpSession.DOM.enable();
      await cdpSession.Accessibility.enable();
      await cdpSession.Runtime.enable();

          
      // Get the document root with full depth
      const { root: rootNode } = await cdpSession.DOM.getDocument({ depth: -1, pierce: true });
      root = rootNode; // Assign the actual node to the root variable

    }
   

    /**
     * Enhanced recursive function to process CDP nodes with deep traversal
     * @param node - CDP DOM node
     * @param parentId - Parent node ID
     * @param depth - Current depth in DOM tree
     */
    function processCDPNode(node: any, parentId?: string, depth: number = 0): void {
      // Avoid infinite loops by checking if we've already processed this node
      if (processedNodeIds.has(node.nodeId)) {
        return;
      }
      processedNodeIds.add(node.nodeId);

      const nodeId = `cdp-${node.nodeId}`;

      // Create the CDP node with enhanced information
      cdpNodes[nodeId] = {
        nodeId: node.nodeId,
        nodeType: node.nodeType,
        nodeName: node.nodeName,
        localName: node.localName,
        nodeValue: node.nodeValue,
        attributes: node.attributes || [],
        children: [],
        shadowRoots: node.shadowRoots || [],
        frameId: node.frameId,
        parentId: parentId ? parseInt(parentId.replace('cdp-', '')) : undefined,
        depth: depth,
        contentDocument: node.contentDocument,
        isDeepTraversed: true
      };

      // Process all children recursively
      if (node.children && Array.isArray(node.children)) {
        for (const child of node.children) {
          // Recursively process child nodes
          processCDPNode(child, nodeId, depth + 1);

          // Add child reference to current node
          if (cdpNodes[nodeId].children) {
            cdpNodes[nodeId].children!.push({
              nodeId: child.nodeId,
              nodeType: child.nodeType,
              nodeName: child.nodeName,
              localName: child.localName,
              nodeValue: child.nodeValue,
              attributes: child.attributes || [],
              parentId: node.nodeId,
              depth: depth + 1
            });
          }
        }
      }

      // Process shadow roots recursively
      if (node.shadowRoots && Array.isArray(node.shadowRoots)) {
        for (const shadowRoot of node.shadowRoots) {
          processCDPNode(shadowRoot, nodeId, depth + 1);
        }
      }

      // Process content document for iframes
      if (node.contentDocument) {
        processCDPNode(node.contentDocument, nodeId, depth + 1);
      }
    }

    // Start processing from the root
    processCDPNode(root);

    // Additional step: Get all nodes using DOM.getFlattenedDocument for comprehensive coverage
    try {
      let nodes;
      if (isPlaywrightPage(page)) {
          ({ nodes } = await cdpSession.send('DOM.getFlattenedDocument', { depth: -1, pierce: true }));
      } else if (isTestCafeController(page)) {
          ({ nodes } = await cdpSession.DOM.getFlattenedDocument({ depth: -1, pierce: true }));
      }

      if (nodes && Array.isArray(nodes)) {
    

        for (const node of nodes) {
          if (!processedNodeIds.has(node.nodeId)) {
            processCDPNode(node, undefined, 0);
          }
        }
      }
    } catch (error) {
      console.warn('CDP: getFlattenedDocument failed, continuing with standard extraction:', error);
    }

    if (isPlaywrightPage(page)) {
      await cdpSession.detach();
    }

        

    return cdpNodes;
  } catch (error) {
    logger.warn('CDP DOM extraction failed:', error);
    return {};
  }
}
// Type guard for TestCafe Controller
function isTestCafeController(obj: any): obj is TestController {
  return typeof obj.click === 'function' && typeof obj.expect === 'function';
}


/**
 * Enhanced Accessibility Tree Strategy: Extract accessibility information
 * @param {Page} page - Playwright page object
 * @returns {Promise<Record<string, AccessibilityTreeNode>>} - Accessibility tree nodes map
 */
export async function extractAccessibilityTreeNodes(page: Page | TestController): Promise<Record<string, AccessibilityTreeNode>> {
  try {
    const accessibilityNodes: Record<string, AccessibilityTreeNode> = {};
    let elements: any[] = [];

    if (isPlaywrightPage(page)) {
      elements = await page.locator('*').all();
    } else if (isTestCafeController(page)) {
      // More efficient selector to target only relevant elements
      const selector = Selector('[role], [aria-label], [aria-labelledby], [aria-describedby], [title], [alt]');
      const count = await selector.count;
      for (let i = 0; i < count; i++) {
        elements.push(selector.nth(i));
      }
    }

    // Define ClientFunction once outside the loop for efficiency with TestCafe
    const getAttribute = ClientFunction((selector: Selector, attr: string) => {
      const el = selector();
      return el ? el.getAttribute(attr) : null;
    });

    for (let i = 0; i < elements.length; i++) {
      try {
        let role, ariaLabel, ariaLabelledBy, ariaDescribedBy, title, alt, textContent;
        let element: any;

        if (isPlaywrightPage(page)) {
          element = elements[i];
          if (!(await element.isVisible())) continue;

          role = await element.getAttribute('role');
          ariaLabel = await element.getAttribute('aria-label');
          ariaLabelledBy = await element.getAttribute('aria-labelledby');
          ariaDescribedBy = await element.getAttribute('aria-describedby');
          title = await element.getAttribute('title');
          alt = await element.getAttribute('alt');
          textContent = await element.textContent();
        } else { // TestCafe Logic
          element = elements[i];
          if (!(await element.visible)) continue; // Check visibility for TestCafe elements

          role = await getAttribute(element, 'role');
          ariaLabel = await getAttribute(element, 'aria-label');
          ariaLabelledBy = await getAttribute(element, 'aria-labelledby');
          ariaDescribedBy = await getAttribute(element, 'aria-describedby');
          title = await getAttribute(element, 'title');
          alt = await getAttribute(element, 'alt');
          textContent = await element.innerText;
        }

        if (role || ariaLabel || ariaLabelledBy || ariaDescribedBy || title || alt) {
          const nodeId = `acc-${i}`;

          // Enhanced accessibility properties based on WAI-ARIA 1.2
          const enhancedProperties: Record<string, any> = {
            'aria-labelledby': ariaLabelledBy,
            'aria-describedby': ariaDescribedBy,
            'aria-description': isPlaywrightPage(page) ? await element.getAttribute('aria-description') : await getAttribute(elements[i], 'aria-description'),
            'aria-expanded': isPlaywrightPage(page) ? await element.getAttribute('aria-expanded') : await getAttribute(elements[i], 'aria-expanded'),
            'aria-selected': isPlaywrightPage(page) ? await element.getAttribute('aria-selected') : await getAttribute(elements[i], 'aria-selected'),
            'aria-checked': isPlaywrightPage(page) ? await element.getAttribute('aria-checked') : await getAttribute(elements[i], 'aria-checked'),
            'aria-pressed': isPlaywrightPage(page) ? await element.getAttribute('aria-pressed') : await getAttribute(elements[i], 'aria-pressed'),
            'aria-current': isPlaywrightPage(page) ? await element.getAttribute('aria-current') : await getAttribute(elements[i], 'aria-current'),
            'aria-invalid': isPlaywrightPage(page) ? await element.getAttribute('aria-invalid') : await getAttribute(elements[i], 'aria-invalid'),
            'aria-required': isPlaywrightPage(page) ? await element.getAttribute('aria-required') : await getAttribute(elements[i], 'aria-required'),
            'aria-readonly': isPlaywrightPage(page) ? await element.getAttribute('aria-readonly') : await getAttribute(elements[i], 'aria-readonly'),
            'aria-multiline': isPlaywrightPage(page) ? await element.getAttribute('aria-multiline') : await getAttribute(elements[i], 'aria-multiline'),
            'aria-multiselectable': isPlaywrightPage(page) ? await element.getAttribute('aria-multiselectable') : await getAttribute(elements[i], 'aria-multiselectable'),
            'aria-orientation': isPlaywrightPage(page) ? await element.getAttribute('aria-orientation') : await getAttribute(elements[i], 'aria-orientation'),
            'aria-sort': isPlaywrightPage(page) ? await element.getAttribute('aria-sort') : await getAttribute(elements[i], 'aria-sort'),
            'aria-level': isPlaywrightPage(page) ? await element.getAttribute('aria-level') : await getAttribute(elements[i], 'aria-level'),
            'aria-posinset': isPlaywrightPage(page) ? await element.getAttribute('aria-posinset') : await getAttribute(elements[i], 'aria-posinset'),
            'aria-setsize': isPlaywrightPage(page) ? await element.getAttribute('aria-setsize') : await getAttribute(elements[i], 'aria-setsize'),
            'aria-valuemin': isPlaywrightPage(page) ? await element.getAttribute('aria-valuemin') : await getAttribute(elements[i], 'aria-valuemin'),
            'aria-valuemax': isPlaywrightPage(page) ? await element.getAttribute('aria-valuemax') : await getAttribute(elements[i], 'aria-valuemax'),
            'aria-valuenow': isPlaywrightPage(page) ? await element.getAttribute('aria-valuenow') : await getAttribute(elements[i], 'aria-valuenow'),
            'aria-valuetext': isPlaywrightPage(page) ? await element.getAttribute('aria-valuetext') : await getAttribute(elements[i], 'aria-valuetext'),
            'aria-live': isPlaywrightPage(page) ? await element.getAttribute('aria-live') : await getAttribute(elements[i], 'aria-live'),
            'aria-relevant': isPlaywrightPage(page) ? await element.getAttribute('aria-relevant') : await getAttribute(elements[i], 'aria-relevant'),
            'aria-atomic': isPlaywrightPage(page) ? await element.getAttribute('aria-atomic') : await getAttribute(elements[i], 'aria-atomic'),
            'aria-busy': isPlaywrightPage(page) ? await element.getAttribute('aria-busy') : await getAttribute(elements[i], 'aria-busy'),
            'aria-modal': isPlaywrightPage(page) ? await element.getAttribute('aria-modal') : await getAttribute(elements[i], 'aria-modal'),
            'aria-haspopup': isPlaywrightPage(page) ? await element.getAttribute('aria-haspopup') : await getAttribute(elements[i], 'aria-haspopup'),
            'aria-controls': isPlaywrightPage(page) ? await element.getAttribute('aria-controls') : await getAttribute(elements[i], 'aria-controls'),
            'aria-owns': isPlaywrightPage(page) ? await element.getAttribute('aria-owns') : await getAttribute(elements[i], 'aria-owns'),
            'aria-flowto': isPlaywrightPage(page) ? await element.getAttribute('aria-flowto') : await getAttribute(elements[i], 'aria-flowto'),
            'aria-activedescendant': isPlaywrightPage(page) ? await element.getAttribute('aria-activedescendant') : await getAttribute(elements[i], 'aria-activedescendant'),
            'aria-colindex': isPlaywrightPage(page) ? await element.getAttribute('aria-colindex') : await getAttribute(elements[i], 'aria-colindex'),
            'aria-colspan': isPlaywrightPage(page) ? await element.getAttribute('aria-colspan') : await getAttribute(elements[i], 'aria-colspan'),
            'aria-rowindex': isPlaywrightPage(page) ? await element.getAttribute('aria-rowindex') : await getAttribute(elements[i], 'aria-rowindex'),
            'aria-rowspan': isPlaywrightPage(page) ? await element.getAttribute('aria-rowspan') : await getAttribute(elements[i], 'aria-rowspan'),
            'aria-colcount': isPlaywrightPage(page) ? await element.getAttribute('aria-colcount') : await getAttribute(elements[i], 'aria-colcount'),
            'aria-rowcount': isPlaywrightPage(page) ? await element.getAttribute('aria-rowcount') : await getAttribute(elements[i], 'aria-rowcount'),
            'tabindex': isPlaywrightPage(page) ? await element.getAttribute('tabindex') : await getAttribute(elements[i], 'tabindex'),
            title,
            alt
          };

          // Filter out undefined values
          const filteredProperties: Record<string, any> = {};
          for (const [key, value] of Object.entries(enhancedProperties)) {
            if (value !== null && value !== undefined) {
              filteredProperties[key] = value;
            }
          }

          accessibilityNodes[nodeId] = {
            nodeId,
            role: role || undefined,
            name: ariaLabel || title || alt || textContent?.trim() || undefined,
            description: ariaDescribedBy || enhancedProperties['aria-description'] || undefined,
            value: enhancedProperties['aria-valuenow'] || enhancedProperties['aria-valuetext'] || undefined,
            properties: filteredProperties
          };
        }
      } catch (error) {
        console.warn(`Skipped element ${i}:`, error);
        continue;
      }
    }

    return accessibilityNodes;
  } catch (error) {
    console.warn('Accessibility tree extraction failed:', error);
    return {};
  }
}

/**
 * Extract selector strategies (CDP and Accessibility Tree) without full element extraction
 * @param {Page} page - Playwright page object
 * @param {ExtractUIElementsOptions} [options] - Options for extraction
 * @returns {Promise<StrategyExtractionResult>} - Strategy extraction results
 */
export async function extractSelectorStrategies(
  page?: Page,
  options: ExtractUIElementsOptions = {}
): Promise<StrategyExtractionResult> {
  const currentPage: any = page;
  const startTime = Date.now();

  const defaultOptions: ExtractUIElementsOptions = {
    enableCDPStrategy: true,
    enableAccessibilityTreeStrategy: true,
    generateWCAGCompliantSelectors: true,
    debugMode: false
  };

  const mergedOptions = { ...defaultOptions, ...options };

  if (mergedOptions.debugMode) {

  }

  try {
    // Initialize strategy data containers
    let cdpNodes: Record<string, CDPDOMNode> = {};
    let accessibilityNodes: Record<string, AccessibilityTreeNode> = {};

    // Extract CDP DOM nodes if enabled
    if (mergedOptions.enableCDPStrategy) {
      if (mergedOptions.debugMode) {
    
      }
      cdpNodes = await extractCDPDOMNodes(currentPage);
      if (mergedOptions.debugMode) {

      }
    }

    // Extract accessibility tree nodes if enabled
    if (mergedOptions.enableAccessibilityTreeStrategy) {
      if (mergedOptions.debugMode) {
    
      }
      accessibilityNodes = await extractAccessibilityTreeNodes(currentPage);
      if (mergedOptions.debugMode) {

      }
    }

    const extractionTime = Date.now() - startTime;

    // Calculate statistics
    const statistics = {
      cdpNodesCount: Object.keys(cdpNodes).length,
      accessibilityNodesCount: Object.keys(accessibilityNodes).length,
      elementsWithCDPSelectors: 0,
      elementsWithWCAGSelectors: 0,
      elementsWithAccessibilitySelectors: 0
    };

    if (mergedOptions.debugMode) {
              
    }

    return {
      cdpNodes,
      accessibilityNodes,
      extractionTime,
      statistics
    };
  } catch (error) {
    logger.error('Error extracting strategies:', error);
    throw new Error(`Failed to extract strategies: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

/**
 * Find all deeply nested interactive elements using CDP
 * @param {Page} page - Playwright page object
 * @param {ExtractUIElementsOptions} [options] - Options for extraction
 * @returns {Promise<DeepInteractiveElement[]>} - Array of deep interactive elements
 */
export async function findDeepInteractiveElements(
  page?: Page,
  options: ExtractUIElementsOptions = {}
): Promise<DeepInteractiveElement[]> {
  const currentPage: any = page;
  const mergedOptions = { ...{ debugMode: false }, ...options };

  if (mergedOptions.debugMode) {

  }

  try {
    // Extract CDP nodes
    const cdpNodes = await extractCDPDOMNodes(currentPage);
    const interactiveElements: DeepInteractiveElement[] = [];

    // Interactive element types and attributes
    const interactiveTypes = ['input', 'button', 'select', 'textarea', 'a', 'form'];
    const interactiveRoles = ['button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'tab', 'menuitem'];

    for (const [nodeId, cdpNode] of Object.entries(cdpNodes)) {
      if (!cdpNode.nodeName) {
          continue; // Skip this node if it doesn't have a name
      }
      const nodeName = cdpNode.nodeName.toLowerCase();
      const attributes: Record<string, string> = {};

      // Parse CDP attributes (stored as array of [name, value, name, value, ...])
      if (cdpNode.attributes && Array.isArray(cdpNode.attributes)) {
        for (let i = 0; i < cdpNode.attributes.length; i += 2) {
          const attrName = cdpNode.attributes[i];
          const attrValue = cdpNode.attributes[i + 1];
          if (attrName && attrValue !== undefined) {
            attributes[attrName] = attrValue;
          }
        }
      }

      // Check if element is interactive
      const isInteractiveType = interactiveTypes.includes(nodeName);
      const hasInteractiveRole = attributes.role && interactiveRoles.includes(attributes.role);
      const hasClickHandler = attributes.onclick || attributes['data-testid'] || attributes['aria-label'];
      const isClickable = attributes.tabindex !== undefined || hasClickHandler;

      if (isInteractiveType || hasInteractiveRole || isClickable) {
        // Generate selectors for this element
        const selectors: string[] = [];

        // ID selector
        if (attributes.id) {
          selectors.push(`#${attributes.id}`);
        }

        // Data-testid selector
        if (attributes['data-testid']) {
          selectors.push(`[data-testid="${attributes['data-testid']}"]`);
        }

        // Aria-label selector
        if (attributes['aria-label']) {
          selectors.push(`[aria-label="${attributes['aria-label']}"]`);
        }

        // Role selector
        if (attributes.role) {
          selectors.push(`[role="${attributes.role}"]`);
        }

        // Class selector
        if (attributes.class) {
          const classes = attributes.class.split(' ').filter(c => c.trim());
          if (classes.length > 0) {
            selectors.push(`.${classes.join('.')}`);
          }
        }

        // Tag selector with attributes
        selectors.push(nodeName);

        // Generate path
        const path = generateElementPath(cdpNode, cdpNodes);

        interactiveElements.push({
          element: cdpNode,
          depth: cdpNode.depth || 0,
          path,
          selectors,
          elementType: nodeName,
          attributes,
          isVisible: true, // Would need additional logic to determine visibility
          isInteractable: !attributes.disabled
        });
      }
    }

    if (mergedOptions.debugMode) {
          

      // Log depth distribution
      const depthStats: Record<number, number> = {};
      interactiveElements.forEach(el => {
        const depth = el.depth;
        depthStats[depth] = (depthStats[depth] || 0) + 1;
      });
  
    }

    return interactiveElements;
  } catch (error) {
    logger.error('Error finding deep interactive elements:', error);
    throw new Error(`Failed to find deep interactive elements: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

/**
 * Generate element path from CDP node hierarchy
 * @param {CDPDOMNode} node - Target CDP node
 * @param {Record<string, CDPDOMNode>} cdpNodes - All CDP nodes
 * @returns {string[]} - Path array
 */
function generateElementPath(node: CDPDOMNode, cdpNodes: Record<string, CDPDOMNode>): string[] {
  const path: string[] = [];
  let currentNode = node;
  let depth = 0;
  const maxDepth = 10;

  while (currentNode && depth < maxDepth) {
    if (!currentNode.nodeName) {
      // If nodeName is missing, we can't process this part of the path.
      // We can either break or continue to the parent. Let's break.
      break;
    }
    let nodeSelector = currentNode.nodeName.toLowerCase();

    // Add identifying attributes if available
    if (currentNode.attributes && Array.isArray(currentNode.attributes)) {
      for (let i = 0; i < currentNode.attributes.length; i += 2) {
        const attrName = currentNode.attributes[i];
        const attrValue = currentNode.attributes[i + 1];

        if (attrName === 'id') {
          nodeSelector = `#${attrValue}`;
          break;
        } else if (attrName === 'class') {
          const classes = attrValue.split(' ').filter(c => c.trim());
          if (classes.length > 0) {
            nodeSelector = `${nodeSelector}.${classes.join('.')}`;
          }
          break;
        }
      }
    }

    path.unshift(nodeSelector);

    // Find parent node
    if (currentNode.parentId) {
      const parentKey = `cdp-${currentNode.parentId}`;
      currentNode = cdpNodes[parentKey];
    } else {
      break;
    }

    depth++;
  }

  return path;
}

/**
 * Extract text content from a CDP node and its children
 * @param {CDPDOMNode} node - Target CDP node
 * @param {Record<string, CDPDOMNode>} cdpNodes - All CDP nodes
 * @returns {string | undefined} - Extracted text content
 */
function extractTextContent(node: CDPDOMNode, cdpNodes: Record<string, CDPDOMNode>): string | undefined {
  let textContent = '';

  // If this is a text node, return its value
  if (node.nodeType === 3 && node.nodeValue) { // TEXT_NODE = 3
    return node.nodeValue.trim();
  }

  // For element nodes, collect text from all text node children
  if (node.children && Array.isArray(node.children)) {
    for (const child of node.children) {
      if (child.nodeType === 3 && child.nodeValue) { // TEXT_NODE
        textContent += child.nodeValue.trim() + ' ';
      } else if (child.nodeType === 1) { // ELEMENT_NODE = 1
        // Recursively get text from child elements
        const childKey = `cdp-${child.nodeId}`;
        const childNode = cdpNodes[childKey];
        if (childNode) {
          const childText = extractTextContent(childNode, cdpNodes);
          if (childText) {
            textContent += childText + ' ';
          }
        }
      }
    }
  }

  // Also check if the node itself has nodeValue (for text nodes)
  if (node.nodeValue && node.nodeValue.trim()) {
    textContent += node.nodeValue.trim();
  }

  const result = textContent.trim();
  return result.length > 0 ? result : undefined;
}

/**
 * Analyze all interactive elements on the page and provide comprehensive statistics
 * @param {Page} page - Playwright page object
 * @param {ExtractUIElementsOptions} [options] - Options for extraction
 * @returns {Promise<InteractiveElementAnalysis>} - Comprehensive analysis results
 */
export async function analyzeAllInteractiveElements(
  page?: Page,
  options: ExtractUIElementsOptions = {}
): Promise<InteractiveElementAnalysis> {
  const currentPage: any = page;
  const mergedOptions = { ...{ debugMode: false }, ...options };

  if (mergedOptions.debugMode) {

  }

  try {
    // Extract CDP nodes directly for more detailed element information
    const cdpNodes = await extractCDPDOMNodes(currentPage);
    const interactiveElements: EnhancedInteractiveElement[] = [];

    // Initialize analysis containers
    const byType: Record<string, number> = {};
    const byDepth: Record<number, number> = {};
    const byRole: Record<string, number> = {};
    let totalDepth = 0;
    let maxDepth = 0;
    let elementsWithIds = 0;
    let elementsWithTestIds = 0;
    let elementsWithAriaLabels = 0;
    let elementsWithRoles = 0;

    // Interactive element types and attributes
    const interactiveTypes = ['input', 'button', 'select', 'textarea', 'a', 'form', 'span'];
    const interactiveRoles = ['button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'tab', 'menuitem'];

    for (const [, cdpNode] of Object.entries(cdpNodes)) {
      if (!cdpNode.nodeName) {
        continue; // Skip this node if it doesn't have a name
      }

      const nodeName = cdpNode.nodeName.toLowerCase();
      const attributes: Record<string, string> = {};

      // Parse CDP attributes (stored as array of [name, value, name, value, ...])
      if (cdpNode.attributes && Array.isArray(cdpNode.attributes)) {
        for (let i = 0; i < cdpNode.attributes.length; i += 2) {
          const attrName = cdpNode.attributes[i];
          const attrValue = cdpNode.attributes[i + 1];
          if (attrName && attrValue !== undefined) {
            attributes[attrName] = attrValue;
          }
        }
      }

      // Check if element is interactive
      const isInteractiveType = interactiveTypes.includes(nodeName);
      const hasInteractiveRole = attributes.role && interactiveRoles.includes(attributes.role);
      const hasClickHandler = attributes.onclick || attributes['data-testid'] || attributes['aria-label'];
      const isClickable = attributes.tabindex !== undefined || hasClickHandler;
      const hasInteractiveClass = attributes.class && (
        attributes.class.includes('MuiButton') ||
        attributes.class.includes('MuiInput') ||
        attributes.class.includes('form-element') ||
        attributes.class.includes('interactive')
      );

      if (isInteractiveType || hasInteractiveRole || isClickable || hasInteractiveClass) {
        // Generate selectors for this element
        const selectors: string[] = [];

        // ID selector
        if (attributes.id) {
          selectors.push(`#${attributes.id}`);
        }

        // Data-testid selector
        if (attributes['data-testid']) {
          selectors.push(`[data-testid="${attributes['data-testid']}"]`);
        }

        // Name attribute selector
        if (attributes.name) {
          selectors.push(`[name="${attributes.name}"]`);
        }

        // Type selector for inputs
        if (attributes.type) {
          selectors.push(`${nodeName}[type="${attributes.type}"]`);
        }

        // Aria-label selector
        if (attributes['aria-label']) {
          selectors.push(`[aria-label="${attributes['aria-label']}"]`);
        }

        // Role selector
        if (attributes.role) {
          selectors.push(`[role="${attributes.role}"]`);
        }

        // Class selectors - break down complex Material-UI classes
        if (attributes.class) {
          const classes = attributes.class.split(' ').filter(c => c.trim());
          if (classes.length > 0) {
            // Add full class selector
            selectors.push(`.${classes.join('.')}`);

            // Add individual important classes
            classes.forEach(cls => {
              if (cls.startsWith('Mui') || cls.includes('form-element') || cls.includes('interactive')) {
                selectors.push(`.${cls}`);
              }
            });
          }
        }

        // Tag selector
        selectors.push(nodeName);

        // Generate path
        const path = generateElementPath(cdpNode, cdpNodes);

        // Determine element type with more specificity
        let elementType = nodeName;
        if (hasInteractiveClass) {
          elementType = `${nodeName}[${hasInteractiveClass ? 'interactive-class' : 'form-element'}]`;
        }

        // Check for test and aria attributes
        const hasTestAttributes = !!(attributes['data-testid'] || attributes.id || attributes.name);
        const hasAriaAttributes = !!(attributes['aria-label'] || attributes.role || attributes['aria-invalid']);

        const depth = cdpNode.depth || 0;
        const enhancedElement: EnhancedInteractiveElement = {
          elementType,
          nodeId: cdpNode.nodeId || 0,
          depth,
          selectors,
          attributes,
          isVisible: true, // Would need additional logic to determine visibility
          isInteractable: !attributes.disabled,
          hasTestAttributes,
          hasAriaAttributes,
          path
        };

        interactiveElements.push(enhancedElement);

        // Update statistics
        byType[elementType] = (byType[elementType] || 0) + 1;
        byDepth[depth] = (byDepth[depth] || 0) + 1;
        totalDepth += depth;
        maxDepth = Math.max(maxDepth, depth);

        if (attributes.role) {
          byRole[attributes.role] = (byRole[attributes.role] || 0) + 1;
          elementsWithRoles++;
        }

        if (attributes.id) elementsWithIds++;
        if (attributes['data-testid']) elementsWithTestIds++;
        if (attributes['aria-label']) elementsWithAriaLabels++;
      }
    }

    const averageDepth = interactiveElements.length > 0 ? totalDepth / interactiveElements.length : 0;
    const total = interactiveElements.length;

    const analysis: InteractiveElementAnalysis = {
      interactiveelement: interactiveElements,
      summary: {
        totalElements: total,
        byType,
        byDepth,
        byRole,
        averageDepth: Math.round(averageDepth * 100) / 100,
        maxDepth,
        elementsWithIds,
        elementsWithTestIds,
        elementsWithAriaLabels,
        elementsWithRoles
      },
      total
    };

    if (mergedOptions.debugMode) {
      
    }

    return analysis;
  } catch (error) {
    logger.error('Error analyzing interactive elements:', error);
    throw new Error(`Failed to analyze interactive elements: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

/**
 * Comprehensive DOM Element Data Extraction for Self-Healing Test Automation
 *
 * This function extracts comprehensive DOM element data using Playwright's CDP session
 * and accessibility snapshot APIs. It provides detailed element analysis with framework
 * detection, multiple locator strategies with confidence scoring, and WCAG-compliant selectors.
 *
 * @param {Page} page - Playwright Page object
 * @param {ExtractUIElementsOptions} [options] - Options for extraction
 * @returns {Promise<ComprehensiveDOMAnalysis>} - Comprehensive DOM analysis result
 */
export async function extractComprehensiveDOMData(
  page: Page,
  options: ExtractUIElementsOptions = {}
): Promise<ComprehensiveDOMAnalysis> {
  
  
  const startTime = Date.now();
  const defaultOptions: ExtractUIElementsOptions = {
    enableCDPStrategy: true,
    enableAccessibilityTreeStrategy: true,
    generateWCAGCompliantSelectors: true,
    includeHidden: false,
    includeIframes: true,
    includeShadowDOM: true,
    debugMode: false,
    maxDepth: -1 // Maximum depth for complete DOM traversal
  };

  const mergedOptions = { ...defaultOptions, ...options };

  if (mergedOptions.debugMode) {

  }

  try {
    // Step 1: Extract page metadata
    const pageUrl = page.url();
    const timestamp = new Date().toISOString();
    const viewport = await page.viewportSize() || { width: 1920, height: 1080 };
    const deviceScaleFactor = await page.evaluate(() => window.devicePixelRatio) || 1;

    if (mergedOptions.debugMode) {

    }

    // Step 2: Extract CDP DOM nodes (Primary Strategy)
    const cdpNodes = await extractCDPDOMNodes(page);
    // Step 3: Extract accessibility tree nodes (Fallback Strategy)
    const accessibilityNodes = await extractAccessibilityTreeNodes(page);

    // Step 4: Process elements and generate comprehensive data
    const elements: ComprehensiveElementData[] = [];
    const statistics = {
      totalElements: 0,
      interactiveElements: 0,
      elementsWithIds: 0,
      elementsWithTestIds: 0,
      elementsWithAriaLabels: 0,
      frameworkComponents: {
        react: 0,
        angular: 0,
        vue: 0,
        materialUI: 0,
        agGrid: 0
      },
      averageConfidenceScore: 0,
      wcagCompliantElements: 0
    };

    let totalConfidenceScore = 0;
    let confidenceCount = 0;

    // Interactive element types for filtering
    const interactiveTypes = [
      'input', 'button', 'select', 'textarea', 'a', 'form', 'span', 'div', 'label', 'fieldset', 'legend',
      'iframe', 'canvas', 'svg', 'video', 'audio', 'picture', 'source', 'track', 'details', 'summary',
      'dialog', 'progress', 'meter', 'output', 'datalist', 'option', 'optgroup', 'map', 'area', 'object',
      'embed', 'param', 'time', 'mark', 'abbr', 'cite', 'q', 'blockquote', 'code', 'pre', 'kbd', 'samp',
      'sub', 'sup', 'ruby', 'rt', 'rp', 'bdi', 'bdo', 'wbr', 'template', 'script', 'noscript', 'style',
      'link', 'meta', 'base', 'body', 'header', 'footer', 'nav', 'section', 'article', 'aside', 'h1',
      'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'caption', 'thead',
      'tbody', 'tfoot', 'tr', 'td', 'th', 'col', 'colgroup', 'figure', 'figcaption', 'main', 'small',
      'big', 'hr', 'br', 'em', 'strong', 'i', 'b', 'u', 's', 'del', 'ins', 'cite', 'dfn', 'var', 'address'
    ];
    const interactiveRoles = [
      // Widget Roles (Interactive)
      'button', 'checkbox', 'gridcell', 'link', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 
      'option', 'progressbar', 'radio', 'scrollbar', 'searchbox', 'slider', 'spinbutton', 'switch', 
      'tab', 'tabpanel', 'textbox', 'combobox', 'listbox', 'menu', 'menubar', 'radiogroup', 'tablist',
      'tree', 'treegrid', 'treeitem', 'grid', 'row', 'cell', 'columnheader', 'rowheader',
      
      // Document Structure Roles (May be interactive)
      'article', 'cell', 'columnheader', 'definition', 'directory', 'document', 'feed', 'figure', 
      'group', 'heading', 'img', 'list', 'listitem', 'math', 'none', 'note', 'presentation', 
      'row', 'rowheader', 'section', 'separator', 'table', 'term', 'text', 'toolbar', 'tooltip',
      
      // Landmark Roles (Navigation)
      'banner', 'complementary', 'contentinfo', 'form', 'main', 'navigation', 'region', 'search',
      
      // Live Region Roles (Dynamic content)
      'alert', 'log', 'marquee', 'status', 'timer',
      
      // Window Roles (Modal/Overlay)
      'alertdialog', 'dialog', 'application', 'banner', 'complementary', 'contentinfo', 'form', 
      'main', 'navigation', 'region', 'search',
      
      // Abstract Roles (Base concepts)
      'command', 'composite', 'input', 'landmark', 'range', 'roletype', 'section', 'sectionhead',
      'select', 'structure', 'tabpanel', 'widget', 'window'
    ];

    for (const [, cdpNode] of Object.entries(cdpNodes)) {
      if (!cdpNode.nodeName) {
        continue; // Skip this node if it doesn't have a name
      }
      const nodeName = cdpNode.nodeName.toLowerCase();
      const attributes: Record<string, string> = {};

      // Parse CDP attributes
      if (cdpNode.attributes && Array.isArray(cdpNode.attributes)) {
        for (let i = 0; i < cdpNode.attributes.length; i += 2) {
          const attrName = cdpNode.attributes[i];
          const attrValue = cdpNode.attributes[i + 1];
          if (attrName && attrValue !== undefined) {
            attributes[attrName] = attrValue;
          }
        }
      }

      // Check if element is interactive or has important attributes
      const isInteractiveType = interactiveTypes.includes(nodeName);
      const hasInteractiveRole = attributes.role && interactiveRoles.includes(attributes.role);
      const hasImportantAttributes = attributes.id || attributes['data-testid'] || attributes['aria-label'] || attributes.role;
      const hasClickHandler = attributes.onclick || attributes.tabindex !== undefined;

      if (isInteractiveType || hasInteractiveRole || hasImportantAttributes || hasClickHandler) {
        // Extract text content from the element and its children
        const textContent = extractTextContent(cdpNode, cdpNodes);

        // Generate locator candidates with confidence scoring
        const locatorCandidates = generateLocatorCandidates(attributes, nodeName, textContent);

        // Detect framework hints
        const frameworkHints = detectFrameworkHints(attributes, nodeName);

        // Generate accessibility data
        const accessibility = generateAccessibilityData(attributes, textContent, cdpNode, cdpNodes, nodeName);

        // Generate visual properties (basic implementation)
        const visual = {
          isVisible: !attributes.hidden && attributes.style !== 'display: none',
          styles: attributes.style ? parseStyleString(attributes.style) : {}
        };

        // Generate parent hierarchy
        const parentHierarchy = generateElementPath(cdpNode, cdpNodes);

        // Detect event handlers
        const eventHandlers = detectEventHandlers(attributes);

        // Determine interaction type
        const interactionType = determineInteractionType(nodeName, attributes);

        const elementData: ComprehensiveElementData = {
          tagName: nodeName,
          nodeId: cdpNode.nodeId,
          nodeType: cdpNode.nodeType,
          attributes,
          textContent: textContent || undefined,
          accessibility,
          visual,
          frameworkHints,
          locatorCandidates,
          parentHierarchy,
          eventHandlers,
          isInteractable: !attributes.disabled && visual.isVisible,
          interactionType
        };

        elements.push(elementData);

        // Update statistics
        statistics.totalElements++;
        if (elementData.isInteractable) statistics.interactiveElements++;
        if (attributes.id) statistics.elementsWithIds++;
        if (attributes['data-testid']) statistics.elementsWithTestIds++;
        if (attributes['aria-label']) statistics.elementsWithAriaLabels++;

        // Framework component counting
        if (frameworkHints.react) statistics.frameworkComponents.react++;
        if (frameworkHints.angular) statistics.frameworkComponents.angular++;
        if (frameworkHints.vue) statistics.frameworkComponents.vue++;
        if (frameworkHints.materialUI) statistics.frameworkComponents.materialUI++;
        if (frameworkHints.agGrid) statistics.frameworkComponents.agGrid++;

        // WCAG compliance counting
        const wcagCompliantSelectors = locatorCandidates.filter(loc => loc.isWCAGCompliant);
        if (wcagCompliantSelectors.length > 0) statistics.wcagCompliantElements++;

        // Confidence score calculation
        if (locatorCandidates.length > 0) {
          const avgConfidence = locatorCandidates.reduce((sum, loc) => sum + loc.confidence, 0) / locatorCandidates.length;
          totalConfidenceScore += avgConfidence;
          confidenceCount++;
        }
      }
    }

    // Calculate average confidence score
    statistics.averageConfidenceScore = confidenceCount > 0 ?
      Math.round((totalConfidenceScore / confidenceCount) * 100) / 100 : 0;

    const extractionTime = Date.now() - startTime;

    const result: ComprehensiveDOMAnalysis = {
      pageUrl,
      timestamp,
      viewport: {
        width: viewport.width,
        height: viewport.height,
        deviceScaleFactor
      },
      elements,
      statistics,
      extractionMetadata: {
        cdpNodesExtracted: Object.keys(cdpNodes).length,
        accessibilityNodesExtracted: Object.keys(accessibilityNodes).length,
        extractionTime,
        options: mergedOptions,
        strategies: ['CDP Session', 'Accessibility Tree', 'WCAG Compliance']
      }
    };



    function simplifyElement(element: any) {
      return {
        tagName: element.tagName || undefined,
        id: element.attributes?.id || undefined,
        class: element.attributes?.class || undefined,
        text: element.textContent || undefined,
        role: element.accessibility?.role || undefined,
        name: element.accessibility?.name || undefined,
        isVisible: element.visual?.isVisible ?? undefined,
        boundingBlock: element.visual?.boundingBox ?? undefined,
        isInteractable: element.isInteractable ?? undefined,
        viewPoint: element.viewPoint || undefined,
        locators: Array.isArray(element.locatorCandidates)
          ? element.locatorCandidates
            .filter((c: any) => c && c.type && c.selector)
            .map((c: any) => ({
              type: c.type,
              selector: c.selector,
              confidence: c.confidence
            }))
          : [],
        parentHierarchy: Array.isArray(element.parentHierarchy) ? element.parentHierarchy.join(' > ') : undefined
      };
    }

    const simplifiedElements: any =  result.elements.map(simplifyElement);
    const cleanedDomAnalysis = simplifiedElements.map((obj: Record<string, any>) => {
    const cleanedObj: { [key: string]: any } = {};
    Object.keys(obj).forEach(key => {
      const value = obj[key];
      if (value !== undefined) {
        cleanedObj[key] = value;
      }
    });
  return cleanedObj;
});
    return {
      pageUrl: page.url(),
      timestamp: new Date().toISOString(),
      viewport: {
        width: 1920,
        height: 1080,
        deviceScaleFactor: 1
      },
      elements: cleanedDomAnalysis,
      statistics: {
        totalElements: cleanedDomAnalysis.length,
        interactiveElements: cleanedDomAnalysis.filter(el => el.isInteractable).length,
        elementsWithIds: cleanedDomAnalysis.filter(el => el.id).length,
        elementsWithTestIds: cleanedDomAnalysis.filter(el => el.testId).length,
        elementsWithAriaLabels: cleanedDomAnalysis.filter(el => el.name).length,
        frameworkComponents: {
          react: 0,
          angular: 0,
          vue: 0,
          materialUI: 0,
          agGrid: 0
        },
        averageConfidenceScore: 0.5,
        wcagCompliantElements: cleanedDomAnalysis.filter(el => el.locators?.some(l => l.isWCAGCompliant)).length
      },
      extractionMetadata: {
        cdpNodesExtracted: cleanedDomAnalysis.length,
        accessibilityNodesExtracted: cleanedDomAnalysis.filter(el => el.name).length,
        extractionTime: Date.now(),
        options: options,
        strategies: ['cdp', 'accessibility']
      }
    };

  } catch (error) {
    logger.error('❌ Error in comprehensive DOM data extraction:', error);
    throw new Error(`Failed to extract comprehensive DOM data: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

/**
 * Generate locator candidates with confidence scoring
 * @param {Record<string, string>} attributes - Element attributes
 * @param {string} tagName - Element tag name
 * @param {string} [textContent] - Element text content
 * @returns {LocatorStrategy[]} - Array of locator strategies with confidence scores
 */
function generateLocatorCandidates(
  attributes: Record<string, string>,
  tagName: string,
  textContent?: string
): LocatorStrategy[] {
  const locators: LocatorStrategy[] = [];

  // ID selector (highest confidence)
  if (attributes.id) {
    locators.push({
      type: 'id',
      selector: `#${attributes.id}`,
      confidence: 0.95,
      isWCAGCompliant: true,
      description: 'ID selector - highest reliability'
    });
  }

  // Data-testid selector (very high confidence)
  if (attributes['data-testid']) {
    locators.push({
      type: 'data-testid',
      selector: `[data-testid="${attributes['data-testid']}"]`,
      confidence: 0.9,
      isWCAGCompliant: true,
      description: 'Test ID selector - designed for testing'
    });
  }

  // Role-based selector (WCAG compliant)
  if (attributes.role) {
    locators.push({
      type: 'getByRole',
      selector: `getByRole('${attributes.role}')`,
      confidence: 0.85,
      isWCAGCompliant: true,
      description: 'Role-based selector - accessibility compliant'
    });
  }

  // Aria-label selector (WCAG compliant)
  if (attributes['aria-label']) {
    locators.push({
      type: 'aria-label',
      selector: `[aria-label="${attributes['aria-label']}"]`,
      confidence: 0.8,
      isWCAGCompliant: true,
      description: 'ARIA label selector - accessibility compliant'
    });
  }

  // Text content selector (medium confidence)
  if (textContent && textContent.trim().length > 0) {
    locators.push({
      type: 'getByText',
      selector: `getByText('${textContent.trim()}')`,
      confidence: 0.7,
      isWCAGCompliant: true,
      description: 'Text content selector - semantic matching'
    });
  }

  // Name attribute selector
  if (attributes.name) {
    locators.push({
      type: 'css',
      selector: `[name="${attributes.name}"]`,
      confidence: 0.75,
      isWCAGCompliant: false,
      description: 'Name attribute selector'
    });
  }

  // Class selector (lower confidence due to potential changes)
  if (attributes.class) {
    const classes = attributes.class.split(' ').filter(c => c.trim());
    if (classes.length > 0) {
      locators.push({
        type: 'css',
        selector: `.${classes.join('.')}`,
        confidence: 0.5,
        isWCAGCompliant: false,
        description: 'Class selector - may change with styling updates'
      });
    }
  }

  // Tag selector (lowest confidence)
  locators.push({
    type: 'css',
    selector: tagName,
    confidence: 0.3,
    isWCAGCompliant: false,
    description: 'Tag selector - lowest specificity'
  });

  return locators.sort((a, b) => b.confidence - a.confidence);
}

/**
 * Detect framework hints from element attributes and tag name
 * @param {Record<string, string>} attributes - Element attributes
 * @param {string} tagName - Element tag name
 * @returns {FrameworkHints} - Framework detection hints
 */
function detectFrameworkHints(attributes: Record<string, string>, tagName: string): FrameworkHints {
  const hints: FrameworkHints = {};

  // React detection
  if (attributes['data-reactroot'] || attributes['data-react-checksum'] ||
    Object.keys(attributes).some(key => key.startsWith('data-react'))) {
    hints.react = {
      componentName: attributes['data-component'] || 'Unknown',
      props: {}
    };
  }

  // Angular detection
  if (attributes['ng-version'] || attributes['ng-app'] ||
    Object.keys(attributes).some(key => key.startsWith('ng-') || key.startsWith('_ng'))) {
    hints.angular = {
      componentName: attributes['ng-component'] || 'Unknown',
      directives: Object.keys(attributes).filter(key => key.startsWith('ng-'))
    };
  }

  // Vue detection
  if (attributes['data-v-'] || Object.keys(attributes).some(key => key.startsWith('data-v-'))) {
    hints.vue = {
      componentName: attributes['data-component'] || 'Unknown',
      props: {}
    };
  }

  // Material-UI detection
  if (attributes.class && (
    attributes.class.includes('Mui') ||
    attributes.class.includes('MuiButton') ||
    attributes.class.includes('MuiInput') ||
    attributes.class.includes('MuiTextField')
  )) {
    const muiClasses = attributes.class.split(' ').filter(c => c.startsWith('Mui'));
    hints.materialUI = {
      componentType: muiClasses[0] || 'Unknown',
      variant: attributes['data-variant'] || 'default'
    };
  }

  // AG-Grid detection
  if (attributes.class && (
    attributes.class.includes('ag-') ||
    attributes.class.includes('ag-grid') ||
    attributes.class.includes('ag-cell')
  )) {
    hints.agGrid = {
      cellType: attributes['col-id'] || 'Unknown',
      columnId: attributes['col-id'],
      rowIndex: attributes['row-index'] ? parseInt(attributes['row-index']) : undefined
    };
  }

  return hints;
}

/**
 * Interface for accessible name calculation context
 */
interface AccessibleNameContext {
  attributes: Record<string, string>;
  textContent?: string;
  cdpNode?: CDPDOMNode;
  cdpNodes?: Record<string, CDPDOMNode>;
  tagName?: string;
}

/**
 * Comprehensive accessible name calculation following W3C standards and handling all edge cases
 * @param {AccessibleNameContext} context - Context for accessible name calculation
 * @returns {string | undefined} - Calculated accessible name
 */
function calculateAccessibleName(context: AccessibleNameContext): string | undefined {
  const { attributes, textContent, cdpNode, cdpNodes, tagName } = context;

  // Step 1: aria-label (highest priority per W3C spec)
  if (attributes['aria-label'] && attributes['aria-label'].trim()) {
    return attributes['aria-label'].trim();
  }

  // Step 2: aria-labelledby reference
  if (attributes['aria-labelledby']) {
    const labelledByIds = attributes['aria-labelledby'].split(/\s+/);
    const labelTexts: string[] = [];

    // In a real implementation, we would look up elements by ID
    // For now, we'll use the attribute value as a fallback
    for (const id of labelledByIds) {
      if (id.trim()) {
        // Try to find referenced element in CDP nodes
        const referencedElement = findElementById(id.trim(), cdpNodes);
        if (referencedElement) {
          const refText = extractTextContent(referencedElement, cdpNodes || {});
          if (refText && refText.trim()) {
            labelTexts.push(refText.trim());
          }
        }
      }
    }

    if (labelTexts.length > 0) {
      return labelTexts.join(' ');
    }
  }

  // Step 3: Associated label elements (for form controls)
  if (isFormControl(tagName, attributes)) {
    const associatedLabel = findAssociatedLabel(attributes, cdpNode, cdpNodes);
    if (associatedLabel && associatedLabel.trim()) {
      return associatedLabel.trim();
    }
  }

  // Step 4: title attribute
  if (attributes.title && attributes.title.trim()) {
    return attributes.title.trim();
  }

  // Step 5: alt attribute (for images and image-like elements)
  if (isImageElement(tagName, attributes) && attributes.alt !== undefined) {
    // Empty alt="" is intentional for decorative images
    return attributes.alt.trim() || undefined;
  }

  // Step 6: placeholder attribute (for form inputs)
  if (isFormInput(tagName, attributes) && attributes.placeholder && attributes.placeholder.trim()) {
    return attributes.placeholder.trim();
  }

  // Step 7: value attribute (for specific form controls)
  if (shouldUseValueAsName(tagName, attributes) && attributes.value && attributes.value.trim()) {
    return attributes.value.trim();
  }

  // Step 8: Enhanced text content extraction
  const enhancedTextContent = extractEnhancedTextContent(context);
  if (enhancedTextContent && enhancedTextContent.trim()) {
    return enhancedTextContent.trim();
  }

  // Step 9: Framework-specific patterns
  const frameworkName = extractFrameworkSpecificName(context);
  if (frameworkName && frameworkName.trim()) {
    return frameworkName.trim();
  }

  // Step 10: Fallback mechanisms
  const fallbackName = extractFallbackName(context);
  if (fallbackName && fallbackName.trim()) {
    return fallbackName.trim();
  }

  // Step 11: Last resort - derive from context
  const contextualName = deriveFromContext(context);
  if (contextualName && contextualName.trim()) {
    return contextualName.trim();
  }

  return undefined;
}

/**
 * Find element by ID in CDP nodes
 */
function findElementById(id: string, cdpNodes?: Record<string, CDPDOMNode>): CDPDOMNode | undefined {
  if (!cdpNodes) return undefined;

  for (const node of Object.values(cdpNodes)) {
    if (node.attributes && Array.isArray(node.attributes)) {
      for (let i = 0; i < node.attributes.length; i += 2) {
        if (node.attributes[i] === 'id' && node.attributes[i + 1] === id) {
          return node;
        }
      }
    }
  }
  return undefined;
}

/**
 * Check if element is a form control
 */
function isFormControl(tagName?: string, attributes?: Record<string, string>): boolean {
  if (!tagName) return false;

  const formControlTags = ['input', 'textarea', 'select', 'button'];
  const formControlRoles = ['textbox', 'combobox', 'listbox', 'button', 'checkbox', 'radio', 'slider', 'spinbutton'];

  return formControlTags.includes(tagName.toLowerCase()) ||
    Boolean(attributes?.role && formControlRoles.includes(attributes.role));
}

/**
 * Check if element is an image or image-like element
 */
function isImageElement(tagName?: string, attributes?: Record<string, string>): boolean {
  if (!tagName) return false;

  const imageTags = ['img', 'area', 'input'];
  const imageRoles = ['img', 'image'];

  return imageTags.includes(tagName.toLowerCase()) ||
    (attributes?.role && imageRoles.includes(attributes.role)) ||
    (tagName.toLowerCase() === 'input' && attributes?.type === 'image');
}

/**
 * Check if element is a form input
 */
function isFormInput(tagName?: string, attributes?: Record<string, string>): boolean {
  if (!tagName) return false;

  return tagName.toLowerCase() === 'input' ||
    tagName.toLowerCase() === 'textarea' ||
    Boolean(attributes?.role && ['textbox', 'searchbox'].includes(attributes.role));
}

/**
 * Check if value attribute should be used as accessible name
 */
function shouldUseValueAsName(tagName?: string, attributes?: Record<string, string>): boolean {
  if (!tagName || !attributes) return false;

  const tagLower = tagName.toLowerCase();

  // For input buttons and submit buttons
  if (tagLower === 'input' && attributes.type &&
    ['button', 'submit', 'reset', 'image'].includes(attributes.type)) {
    return true;
  }

  // For range inputs, the value can be meaningful
  if (tagLower === 'input' && attributes.type === 'range') {
    return true;
  }

  return false;
}

/**
 * Find associated label for form controls
 */
function findAssociatedLabel(
  attributes: Record<string, string>,
  cdpNode?: CDPDOMNode,
  cdpNodes?: Record<string, CDPDOMNode>
): string | undefined {
  if (!cdpNodes || !cdpNode) return undefined;

  // Method 1: Explicit association via id and for attribute
  if (attributes.id) {
    for (const node of Object.values(cdpNodes)) {
      if (node.nodeName && node.nodeName.toLowerCase() === 'label' && node.attributes) {
        for (let i = 0; i < node.attributes.length; i += 2) {
          if (node.attributes[i] === 'for' && node.attributes[i + 1] === attributes.id) {
            const labelText = extractTextContent(node, cdpNodes);
            if (labelText && labelText.trim()) {
              return labelText.trim();
            }
          }
        }
      }
    }
  }

  // Method 2: Implicit association (label wrapping the input)
  const parentLabel = findParentLabel(cdpNode, cdpNodes);
  if (parentLabel) {
    const labelText = extractTextContent(parentLabel, cdpNodes);
    if (labelText && labelText.trim()) {
      return labelText.trim();
    }
  }

  return undefined;
}

/**
 * Find parent label element
 */
function findParentLabel(cdpNode: CDPDOMNode, cdpNodes: Record<string, CDPDOMNode>): CDPDOMNode | undefined {
  if (!cdpNode.parentId) return undefined;

  const parentKey = `cdp-${cdpNode.parentId}`;
  const parent = cdpNodes[parentKey];

  if (!parent) return undefined;

  if (parent.nodeName.toLowerCase() === 'label') {
    return parent;
  }

  // Recursively check parent's parent
  return findParentLabel(parent, cdpNodes);
}

/**
 * Enhanced text content extraction with framework awareness
 */
function extractEnhancedTextContent(context: AccessibleNameContext): string | undefined {
  const { textContent, cdpNode, cdpNodes, attributes } = context;

  // Start with basic text content
  let enhancedText = textContent || '';

  // Handle Material-UI specific patterns
  if (attributes?.class && attributes.class.includes('Mui')) {
    enhancedText = extractMaterialUIText(cdpNode, cdpNodes) || enhancedText;
  }

  // Handle React specific patterns
  if (hasReactAttributes(attributes)) {
    enhancedText = extractReactText(cdpNode, cdpNodes) || enhancedText;
  }

  // Handle Angular specific patterns
  if (hasAngularAttributes(attributes)) {
    enhancedText = extractAngularText(cdpNode, cdpNodes) || enhancedText;
  }

  // Handle Vue specific patterns
  if (hasVueAttributes(attributes)) {
    enhancedText = extractVueText(cdpNode, cdpNodes) || enhancedText;
  }

  // Clean up whitespace and return
  const cleaned = enhancedText.replace(/\s+/g, ' ').trim();
  return cleaned.length > 0 ? cleaned : undefined;
}

/**
 * Extract framework-specific accessible names
 */
function extractFrameworkSpecificName(context: AccessibleNameContext): string | undefined {
  const { attributes, cdpNode, cdpNodes } = context;

  // Material-UI specific extraction
  if (attributes?.class && attributes.class.includes('Mui')) {
    // Look for nested spans with text content
    const muiText = extractNestedText(cdpNode, cdpNodes, ['span', 'div']);
    if (muiText) return muiText;
  }

  // React specific extraction
  if (hasReactAttributes(attributes)) {
    // Look for data attributes that might contain text
    const reactText = extractFromDataAttributes(attributes, ['data-text', 'data-label', 'data-content']);
    if (reactText) return reactText;
  }

  // Angular specific extraction
  if (hasAngularAttributes(attributes)) {
    // Look for Angular interpolation patterns
    const angularText = extractAngularInterpolatedText(cdpNode, cdpNodes);
    if (angularText) return angularText;
  }

  return undefined;
}

/**
 * Fallback name extraction mechanisms
 */
function extractFallbackName(context: AccessibleNameContext): string | undefined {
  const { attributes, cdpNode, cdpNodes, tagName } = context;

  // Fallback 1: Look for nearby label elements (siblings)
  const siblingLabel = findSiblingLabel(cdpNode, cdpNodes);
  if (siblingLabel) return siblingLabel;

  // Fallback 2: Look for parent element with meaningful text
  const parentText = extractParentContextText(cdpNode, cdpNodes);
  if (parentText) return parentText;

  // Fallback 3: Look for child elements with specific roles
  const childText = extractChildTextByRole(cdpNode, cdpNodes, ['text', 'label']);
  if (childText) return childText;

  // Fallback 4: Extract from common data attributes
  const dataAttrText = extractFromDataAttributes(attributes, [
    'data-label', 'data-text', 'data-content', 'data-title',
    'data-name', 'data-tooltip', 'data-hint'
  ]);
  if (dataAttrText) return dataAttrText;

  return undefined;
}

/**
 * Derive accessible name from element context
 */
function deriveFromContext(context: AccessibleNameContext): string | undefined {
  const { attributes, cdpNode, cdpNodes, tagName } = context;

  // For buttons without text, look for icon descriptions
  if (tagName === 'button' || attributes?.role === 'button') {
    const iconDesc = extractIconDescription(cdpNode, cdpNodes);
    if (iconDesc) return iconDesc;
  }

  // For links, use href as last resort
  if (tagName === 'a' && attributes?.href) {
    const url = new URL(attributes.href, 'http://example.com');
    return url.pathname.split('/').pop() || 'Link';
  }

  // For form inputs, use name or type
  if (tagName === 'input') {
    if (attributes?.name) return attributes.name.replace(/[-_]/g, ' ');
    if (attributes?.type) return `${attributes.type} input`;
  }

  return undefined;
}

// Helper functions for framework detection and text extraction

function hasReactAttributes(attributes?: Record<string, string>): boolean {
  if (!attributes) return false;
  return Object.keys(attributes).some(key =>
    key.startsWith('data-react') || key.startsWith('_react')
  );
}

function hasAngularAttributes(attributes?: Record<string, string>): boolean {
  if (!attributes) return false;
  return Object.keys(attributes).some(key =>
    key.startsWith('ng-') || key.startsWith('_ng') || key === 'ng-version'
  );
}

function hasVueAttributes(attributes?: Record<string, string>): boolean {
  if (!attributes) return false;
  return Object.keys(attributes).some(key => key.startsWith('data-v-'));
}

function extractMaterialUIText(cdpNode?: CDPDOMNode, cdpNodes?: Record<string, CDPDOMNode>): string | undefined {
  if (!cdpNode || !cdpNodes) return undefined;

  // Material-UI often nests text in spans, look for text in immediate children
  return extractNestedText(cdpNode, cdpNodes, ['span'], 2);
}

function extractReactText(cdpNode?: CDPDOMNode, cdpNodes?: Record<string, CDPDOMNode>): string | undefined {
  if (!cdpNode || !cdpNodes) return undefined;

  // React components might have text in various child elements
  return extractNestedText(cdpNode, cdpNodes, ['span', 'div', 'p'], 3);
}

function extractAngularText(cdpNode?: CDPDOMNode, cdpNodes?: Record<string, CDPDOMNode>): string | undefined {
  if (!cdpNode || !cdpNodes) return undefined;

  // Angular might use interpolation, look for text nodes
  return extractTextContent(cdpNode, cdpNodes);
}

function extractVueText(cdpNode?: CDPDOMNode, cdpNodes?: Record<string, CDPDOMNode>): string | undefined {
  if (!cdpNode || !cdpNodes) return undefined;

  // Vue components similar to React
  return extractNestedText(cdpNode, cdpNodes, ['span', 'div'], 2);
}

function extractNestedText(
  cdpNode?: CDPDOMNode,
  cdpNodes?: Record<string, CDPDOMNode>,
  targetTags: string[] = ['span', 'div'],
  maxDepth: number = 2
): string | undefined {
  if (!cdpNode || !cdpNodes || maxDepth <= 0) return undefined;

  let collectedText = '';

  if (cdpNode.children && Array.isArray(cdpNode.children)) {
    for (const child of cdpNode.children) {
      if (child.nodeType === 3 && child.nodeValue) { // TEXT_NODE
        collectedText += child.nodeValue.trim() + ' ';
      } else if (child.nodeType === 1 && targetTags.includes(child.nodeName.toLowerCase())) {
        const childKey = `cdp-${child.nodeId}`;
        const childNode = cdpNodes[childKey];
        if (childNode) {
          const childText = extractNestedText(childNode, cdpNodes, targetTags, maxDepth - 1);
          if (childText) {
            collectedText += childText + ' ';
          }
        }
      }
    }
  }

  const result = collectedText.trim();
  return result.length > 0 ? result : undefined;
}

function extractFromDataAttributes(attributes: Record<string, string>, dataAttrs: string[]): string | undefined {
  for (const attr of dataAttrs) {
    if (attributes[attr] && attributes[attr].trim()) {
      return attributes[attr].trim();
    }
  }
  return undefined;
}

function extractAngularInterpolatedText(cdpNode?: CDPDOMNode, cdpNodes?: Record<string, CDPDOMNode>): string | undefined {
  // This would need more sophisticated parsing for Angular interpolation
  // For now, fall back to standard text extraction
  return cdpNode && cdpNodes ? extractTextContent(cdpNode, cdpNodes) : undefined;
}

function findSiblingLabel(cdpNode?: CDPDOMNode, cdpNodes?: Record<string, CDPDOMNode>): string | undefined {
  if (!cdpNode || !cdpNodes || !cdpNode.parentId) return undefined;

  const parentKey = `cdp-${cdpNode.parentId}`;
  const parent = cdpNodes[parentKey];
  if (!parent || !parent.children) return undefined;

  // Look for label siblings
  for (const sibling of parent.children) {
    if (sibling.nodeName.toLowerCase() === 'label') {
      const siblingKey = `cdp-${sibling.nodeId}`;
      const siblingNode = cdpNodes[siblingKey];
      if (siblingNode) {
        const labelText = extractTextContent(siblingNode, cdpNodes);
        if (labelText && labelText.trim()) {
          return labelText.trim();
        }
      }
    }
  }

  return undefined;
}

function extractParentContextText(cdpNode?: CDPDOMNode, cdpNodes?: Record<string, CDPDOMNode>): string | undefined {
  if (!cdpNode || !cdpNodes || !cdpNode.parentId) return undefined;

  const parentKey = `cdp-${cdpNode.parentId}`;
  const parent = cdpNodes[parentKey];
  if (!parent) return undefined;

  // Look for meaningful parent text (excluding the current element's text)
  const parentText = extractTextContent(parent, cdpNodes);
  const currentText = extractTextContent(cdpNode, cdpNodes);

  if (parentText && currentText && parentText !== currentText) {
    // Remove current element's text from parent text
    const contextText = parentText.replace(currentText, '').trim();
    return contextText.length > 0 ? contextText : undefined;
  }

  return parentText && parentText.trim() ? parentText.trim() : undefined;
}

function extractChildTextByRole(
  cdpNode?: CDPDOMNode,
  cdpNodes?: Record<string, CDPDOMNode>,
  roles: string[] = []
): string | undefined {
  if (!cdpNode || !cdpNodes || !cdpNode.children) return undefined;

  for (const child of cdpNode.children) {
    const childKey = `cdp-${child.nodeId}`;
    const childNode = cdpNodes[childKey];
    if (childNode && childNode.attributes) {
      // Check if child has one of the target roles
      for (let i = 0; i < childNode.attributes.length; i += 2) {
        if (childNode.attributes[i] === 'role' && roles.includes(childNode.attributes[i + 1])) {
          const childText = extractTextContent(childNode, cdpNodes);
          if (childText && childText.trim()) {
            return childText.trim();
          }
        }
      }
    }
  }

  return undefined;
}

function extractIconDescription(cdpNode?: CDPDOMNode, cdpNodes?: Record<string, CDPDOMNode>): string | undefined {
  if (!cdpNode || !cdpNodes) return undefined;

  // Look for common icon patterns
  const iconSelectors = ['i', 'svg', 'use'];

  if (cdpNode.children) {
    for (const child of cdpNode.children) {
      if (iconSelectors.includes(child.nodeName.toLowerCase())) {
        const childKey = `cdp-${child.nodeId}`;
        const childNode = cdpNodes[childKey];
        if (childNode && childNode.attributes) {
          // Look for icon descriptions in common attributes
          for (let i = 0; i < childNode.attributes.length; i += 2) {
            const attrName = childNode.attributes[i];
            const attrValue = childNode.attributes[i + 1];

            if (['title', 'aria-label', 'data-icon', 'class'].includes(attrName) && attrValue) {
              if (attrName === 'class') {
                // Extract meaningful class names for icons
                const iconClass = attrValue.split(' ').find(cls =>
                  cls.includes('icon') || cls.includes('fa-') || cls.includes('material-icons')
                );
                if (iconClass) {
                  return iconClass.replace(/[-_]/g, ' ').replace(/^(fa-|icon-|material-icons-)/, '');
                }
              } else {
                return attrValue;
              }
            }
          }
        }
      }
    }
  }

  return undefined;
}

/**
 * Generate accessibility data from element attributes and text content
 * @param {Record<string, string>} attributes - Element attributes
 * @param {string} [textContent] - Element text content
 * @param {CDPDOMNode} [cdpNode] - CDP DOM node for advanced extraction
 * @param {Record<string, CDPDOMNode>} [cdpNodes] - All CDP nodes for context
 * @param {string} [tagName] - Element tag name
 * @returns {object} - Accessibility data object
 */
function generateAccessibilityData(
  attributes: Record<string, string>,
  textContent?: string,
  cdpNode?: CDPDOMNode,
  cdpNodes?: Record<string, CDPDOMNode>,
  tagName?: string
) {
  // Use comprehensive accessible name calculation
  const accessibleName = calculateAccessibleName({
    attributes,
    textContent,
    cdpNode,
    cdpNodes,
    tagName
  });

  // Extract all ARIA attributes based on WAI-ARIA 1.2 specification
  const ariaAttributes = extractARIAttributes(attributes);
  
  // Determine semantic role
  const semanticRole = determineSemanticRole(attributes, tagName);
  
  // Extract live region information
  const liveRegion = extractLiveRegionInfo(attributes);
  
  // Extract form control information
  const formControl = extractFormControlInfo(attributes);
  
  // Extract landmark information
  const landmark = extractLandmarkInfo(attributes);
  
  // Extract widget information
  const widget = extractWidgetInfo(attributes);
  
  // Extract relationship information
  const relationships = extractRelationshipInfo(attributes);

  return {
    // Basic accessibility properties
    role: attributes.role || semanticRole,
    name: accessibleName,
    description: attributes['aria-description'] || extractAriaDescription(attributes, cdpNodes),
    
    // ARIA labels and descriptions
    ariaLabel: attributes['aria-label'],
    ariaLabelledBy: attributes['aria-labelledby'],
    ariaDescribedBy: attributes['aria-describedby'],
    
    // ARIA states (Widget Attributes)
    ariaExpanded: attributes['aria-expanded'] === 'true',
    ariaSelected: attributes['aria-selected'] === 'true',
    ariaChecked: attributes['aria-checked'] === 'true',
    ariaDisabled: attributes['aria-disabled'] === 'true',
    ariaHidden: attributes['aria-hidden'] === 'true',
    ariaPressed: attributes['aria-pressed'] === 'true',
    ariaCurrent: attributes['aria-current'],
    ariaInvalid: attributes['aria-invalid'],
    ariaRequired: attributes['aria-required'] === 'true',
    ariaReadOnly: attributes['aria-readonly'] === 'true',
    ariaMultiLine: attributes['aria-multiline'] === 'true',
    ariaMultiSelectable: attributes['aria-multiselectable'] === 'true',
    ariaOrientation: attributes['aria-orientation'],
    ariaSort: attributes['aria-sort'],
    ariaGrabbed: attributes['aria-grabbed'],
    ariaDropeffect: attributes['aria-dropeffect'],
    
    // ARIA properties (Relationship Attributes)
    ariaActivedescendant: attributes['aria-activedescendant'],
    ariaControls: attributes['aria-controls'],
    ariaOwns: attributes['aria-owns'],
    ariaFlowto: attributes['aria-flowto'],
    
    // Live Region Attributes
    ariaLive: attributes['aria-live'],
    ariaRelevant: attributes['aria-relevant'],
    ariaAtomic: attributes['aria-atomic'] === 'true',
    ariaBusy: attributes['aria-busy'] === 'true',
    
    // Window Attributes
    ariaModal: attributes['aria-modal'] === 'true',
    ariaHaspopup: attributes['aria-haspopup'],
    
    // Range Attributes
    ariaLevel: attributes['aria-level'] ? parseInt(attributes['aria-level']) : undefined,
    ariaPosinset: attributes['aria-posinset'] ? parseInt(attributes['aria-posinset']) : undefined,
    ariaSetsize: attributes['aria-setsize'] ? parseInt(attributes['aria-setsize']) : undefined,
    ariaValueMin: attributes['aria-valuemin'] ? parseFloat(attributes['aria-valuemin']) : undefined,
    ariaValueMax: attributes['aria-valuemax'] ? parseFloat(attributes['aria-valuemax']) : undefined,
    ariaValueNow: attributes['aria-valuenow'] ? parseFloat(attributes['aria-valuenow']) : undefined,
    ariaValueText: attributes['aria-valuetext'],
    
    // Table Attributes
    ariaColindex: attributes['aria-colindex'] ? parseInt(attributes['aria-colindex']) : undefined,
    ariaColspan: attributes['aria-colspan'] ? parseInt(attributes['aria-colspan']) : undefined,
    ariaRowindex: attributes['aria-rowindex'] ? parseInt(attributes['aria-rowindex']) : undefined,
    ariaRowspan: attributes['aria-rowspan'] ? parseInt(attributes['aria-rowspan']) : undefined,
    ariaColcount: attributes['aria-colcount'] ? parseInt(attributes['aria-colcount']) : undefined,
    ariaRowcount: attributes['aria-rowcount'] ? parseInt(attributes['aria-rowcount']) : undefined,
    
    // Tab index and keyboard navigation
    tabIndex: attributes.tabindex ? parseInt(attributes.tabindex) : undefined,
    tabStop: attributes.tabindex !== '-1',
    
    // Semantic information
    semanticLabel: accessibleName,
    semanticRole: semanticRole,
    
    // Live region information
    liveRegion,
    
    // Form control information
    formControl,
    
    // Landmark information
    landmark,
    
    // Widget information
    widget,
    
    // Relationship information
    relationships,
    
    // All ARIA attributes for comprehensive analysis
    ariaAttributes,
    
    // Accessibility compliance
    isAccessible: isElementAccessible(attributes, accessibleName),
    accessibilityIssues: detectAccessibilityIssues(attributes, accessibleName, tagName),
    
    // Focus management
    focusable: isElementFocusable(attributes, tagName),
    focusVisible: attributes['data-focus-visible'] === 'true' || attributes['data-focus-visible'] === '',
    
    // Screen reader support
    screenReaderText: generateScreenReaderText(attributes, accessibleName, textContent),
    
    // Keyboard navigation support
    keyboardNavigation: {
      tabbable: attributes.tabindex !== '-1',
      enterKey: attributes['data-enter-key'] === 'true',
      spaceKey: attributes['data-space-key'] === 'true',
      arrowKeys: attributes['data-arrow-keys'] === 'true'
    }
  };
}

/**
 * Extract all ARIA attributes from element attributes
 * @param {Record<string, string>} attributes - Element attributes
 * @returns {Record<string, string>} - ARIA attributes only
 */
function extractARIAttributes(attributes: Record<string, string>): Record<string, string> {
  const ariaAttrs: Record<string, string> = {};
  
  for (const [key, value] of Object.entries(attributes)) {
    if (key.startsWith('aria-')) {
      ariaAttrs[key] = value;
    }
  }
  
  return ariaAttrs;
}

/**
 * Determine semantic role based on HTML tag and ARIA attributes
 * @param {Record<string, string>} attributes - Element attributes
 * @param {string} [tagName] - Element tag name
 * @returns {string | undefined} - Semantic role
 */
function determineSemanticRole(attributes: Record<string, string>, tagName?: string): string | undefined {
  // Check explicit ARIA role first
  if (attributes.role) {
    return attributes.role;
  }
  
  // Map HTML tags to semantic roles based on WAI-ARIA 1.2
  const semanticRoleMap: Record<string, string> = {
    'button': 'button',
    'input': getInputRole(attributes),
    'a': 'link',
    'nav': 'navigation',
    'main': 'main',
    'header': 'banner',
    'footer': 'contentinfo',
    'aside': 'complementary',
    'section': 'region',
    'article': 'article',
    'h1': 'heading',
    'h2': 'heading',
    'h3': 'heading',
    'h4': 'heading',
    'h5': 'heading',
    'h6': 'heading',
    'form': 'form',
    'table': 'table',
    'ul': 'list',
    'ol': 'list',
    'li': 'listitem',
    'img': 'img',
    'video': 'video',
    'audio': 'audio',
    'progress': 'progressbar',
    'meter': 'meter',
    'select': 'combobox',
    'textarea': 'textbox',
    'fieldset': 'group',
    'legend': 'group',
    'dialog': 'dialog',
    'menu': 'menu',
    'menuitem': 'menuitem',
    'tab': 'tab',
    'tabpanel': 'tabpanel',
    'toolbar': 'toolbar',
    'tooltip': 'tooltip',
    'status': 'status',
    'alert': 'alert',
    'log': 'log',
    'marquee': 'marquee',
    'timer': 'timer',
    'separator': 'separator',
    'slider': 'slider',
    'spinbutton': 'spinbutton',
    'switch': 'switch',
    'checkbox': 'checkbox',
    'radio': 'radio',
    'grid': 'grid',
    'tree': 'tree',
    'treeitem': 'treeitem',
    'row': 'row',
    'cell': 'cell',
    'columnheader': 'columnheader',
    'rowheader': 'rowheader',
    'application': 'application',
    'banner': 'banner',
    'complementary': 'complementary',
    'contentinfo': 'contentinfo',
    'definition': 'definition',
    'directory': 'directory',
    'document': 'document',
    'feed': 'feed',
    'figure': 'figure',
    'group': 'group',
    'none': 'none',
    'note': 'note',
    'presentation': 'presentation',
    'search': 'search',
    'term': 'term',
    'text': 'text',
    'treegrid': 'treegrid',
    'widget': 'widget',
    'window': 'window'
  };
  
  return tagName ? semanticRoleMap[tagName.toLowerCase()] : undefined;
}

/**
 * Get input role based on input type
 * @param {Record<string, string>} attributes - Element attributes
 * @returns {string} - Input role
 */
function getInputRole(attributes: Record<string, string>): string {
  const type = attributes.type?.toLowerCase();
  
  switch (type) {
    case 'button':
    case 'submit':
    case 'reset':
      return 'button';
    case 'checkbox':
      return 'checkbox';
    case 'radio':
      return 'radio';
    case 'range':
      return 'slider';
    case 'search':
      return 'searchbox';
    case 'tel':
    case 'email':
    case 'url':
    case 'number':
    case 'password':
    case 'text':
    default:
      return 'textbox';
  }
}

/**
 * Extract live region information
 * @param {Record<string, string>} attributes - Element attributes
 * @returns {LiveRegionInfo} - Live region information
 */
function extractLiveRegionInfo(attributes: Record<string, string>) {
  return {
    live: attributes['aria-live'] || 'off',
    relevant: attributes['aria-relevant'] || 'additions text',
    atomic: attributes['aria-atomic'] === 'true',
    busy: attributes['aria-busy'] === 'true'
  };
}

/**
 * Extract form control information
 * @param {Record<string, string>} attributes - Element attributes
 * @returns {FormControlInfo} - Form control information
 */
function extractFormControlInfo(attributes: Record<string, string>) {
  return {
    required: attributes['aria-required'] === 'true',
    invalid: attributes['aria-invalid'],
    readOnly: attributes['aria-readonly'] === 'true',
    multiLine: attributes['aria-multiline'] === 'true',
    multiSelectable: attributes['aria-multiselectable'] === 'true',
    orientation: attributes['aria-orientation'],
    valueMin: attributes['aria-valuemin'] ? parseFloat(attributes['aria-valuemin']) : undefined,
    valueMax: attributes['aria-valuemax'] ? parseFloat(attributes['aria-valuemax']) : undefined,
    valueNow: attributes['aria-valuenow'] ? parseFloat(attributes['aria-valuenow']) : undefined,
    valueText: attributes['aria-valuetext']
  };
}

/**
 * Extract landmark information
 * @param {Record<string, string>} attributes - Element attributes
 * @returns {LandmarkInfo} - Landmark information
 */
function extractLandmarkInfo(attributes: Record<string, string>) {
  return {
    role: attributes.role,
    label: attributes['aria-label'],
    labelledBy: attributes['aria-labelledby'],
    describedBy: attributes['aria-describedby'],
    description: attributes['aria-description']
  };
}

/**
 * Extract widget information
 * @param {Record<string, string>} attributes - Element attributes
 * @returns {WidgetInfo} - Widget information
 */
function extractWidgetInfo(attributes: Record<string, string>) {
  return {
    expanded: attributes['aria-expanded'] === 'true',
    selected: attributes['aria-selected'] === 'true',
    checked: attributes['aria-checked'] === 'true',
    pressed: attributes['aria-pressed'] === 'true',
    current: attributes['aria-current'],
    hasPopup: attributes['aria-haspopup'],
    modal: attributes['aria-modal'] === 'true',
    sort: attributes['aria-sort'],
    grabbed: attributes['aria-grabbed'],
    dropeffect: attributes['aria-dropeffect']
  };
}

/**
 * Extract relationship information
 * @param {Record<string, string>} attributes - Element attributes
 * @returns {RelationshipInfo} - Relationship information
 */
function extractRelationshipInfo(attributes: Record<string, string>) {
  return {
    activeDescendant: attributes['aria-activedescendant'],
    controls: attributes['aria-controls'],
    owns: attributes['aria-owns'],
    flowTo: attributes['aria-flowto'],
    describedBy: attributes['aria-describedby'],
    labelledBy: attributes['aria-labelledby']
  };
}

/**
 * Extract ARIA description
 * @param {Record<string, string>} attributes - Element attributes
 * @param {Record<string, CDPDOMNode>} [cdpNodes] - All CDP DOM nodes
 * @returns {string | undefined} - ARIA description
 */
function extractAriaDescription(attributes: Record<string, string>, cdpNodes?: Record<string, CDPDOMNode>): string | undefined {
  if (attributes['aria-description']) {
    return attributes['aria-description'];
  }
  
  if (attributes['aria-describedby']) {
    // Try to find the described element and extract its text content
    const describedIds = attributes['aria-describedby'].split(/\s+/);
    for (const id of describedIds) {
      for (const [, node] of Object.entries(cdpNodes || {})) {
        if (node.attributes && node.attributes.includes(id)) {
          // Extract text content from the described element
          return extractTextContent(node, cdpNodes || {});
        }
      }
    }
  }
  
  return undefined;
}

/**
 * Check if element is accessible
 * @param {Record<string, string>} attributes - Element attributes
 * @param {string} [accessibleName] - Accessible name
 * @returns {boolean} - Whether element is accessible
 */
function isElementAccessible(attributes: Record<string, string>, accessibleName?: string): boolean {
  // Element is not accessible if it's hidden
  if (attributes['aria-hidden'] === 'true' || attributes.hidden === 'true') {
    return false;
  }
  
  // Element should have an accessible name
  if (!accessibleName || accessibleName.trim() === '') {
    return false;
  }
  
  // Element should have a valid role
  const role = attributes.role;
  if (role && role !== 'presentation' && role !== 'none') {
    return true;
  }
  
  // Native HTML elements are accessible by default
  return true;
}

/**
 * Detect accessibility issues
 * @param {Record<string, string>} attributes - Element attributes
 * @param {string} [accessibleName] - Accessible name
 * @param {string} [tagName] - Element tag name
 * @returns {string[]} - Array of accessibility issues
 */
function detectAccessibilityIssues(attributes: Record<string, string>, accessibleName?: string, tagName?: string): string[] {
  const issues: string[] = [];
  
  // Missing accessible name
  if (!accessibleName || accessibleName.trim() === '') {
    issues.push('Missing accessible name');
  }
  
  // Missing role for custom widgets
  if (tagName === 'div' || tagName === 'span') {
    if (!attributes.role && !attributes.onclick && !attributes.tabindex) {
      issues.push('Custom element missing ARIA role');
    }
  }
  
  // Invalid ARIA attributes
  const invalidAriaAttrs = ['aria-invalid', 'aria-required', 'aria-readonly'];
  for (const attr of invalidAriaAttrs) {
    if (attributes[attr] && !['true', 'false'].includes(attributes[attr])) {
      issues.push(`Invalid ${attr} value: ${attributes[attr]}`);
    }
  }
  
  // Missing required attributes for certain roles
  const role = attributes.role;
  if (role === 'checkbox' && attributes['aria-checked'] === undefined) {
    issues.push('Checkbox missing aria-checked attribute');
  }
  
  if (role === 'radio' && attributes['aria-checked'] === undefined) {
    issues.push('Radio button missing aria-checked attribute');
  }
  
  if (role === 'slider' && attributes['aria-valuemin'] === undefined) {
    issues.push('Slider missing aria-valuemin attribute');
  }
  
  return issues;
}

/**
 * Check if element is focusable
 * @param {Record<string, string>} attributes - Element attributes
 * @param {string} [tagName] - Element tag name
 * @returns {boolean} - Whether element is focusable
 */
function isElementFocusable(attributes: Record<string, string>, tagName?: string): boolean {
  // Elements with tabindex are focusable
  if (attributes.tabindex !== undefined) {
    return attributes.tabindex !== '-1';
  }
  
  // Native focusable elements
  const focusableTags = ['button', 'input', 'select', 'textarea', 'a', 'area'];
  if (tagName && focusableTags.includes(tagName.toLowerCase())) {
    return true;
  }
  
  // Elements with click handlers are focusable
  if (attributes.onclick) {
    return true;
  }
  
  return false;
}

/**
 * Generate screen reader text
 * @param {Record<string, string>} attributes - Element attributes
 * @param {string} [accessibleName] - Accessible name
 * @param {string} [textContent] - Text content
 * @returns {string} - Screen reader text
 */
function generateScreenReaderText(attributes: Record<string, string>, accessibleName?: string, textContent?: string): string {
  let screenReaderText = '';
  
  // Start with accessible name
  if (accessibleName) {
    screenReaderText += accessibleName;
  }
  
  // Add role information
  const role = attributes.role;
  if (role) {
    screenReaderText += `, ${role}`;
  }
  
  // Add state information
  const states = [];
  if (attributes['aria-expanded'] === 'true') states.push('expanded');
  if (attributes['aria-selected'] === 'true') states.push('selected');
  if (attributes['aria-checked'] === 'true') states.push('checked');
  if (attributes['aria-pressed'] === 'true') states.push('pressed');
  if (attributes['aria-required'] === 'true') states.push('required');
  if (attributes['aria-invalid'] === 'true') states.push('invalid');
  
  if (states.length > 0) {
    screenReaderText += `, ${states.join(', ')}`;
  }
  
  // Add value information for range inputs
  if (attributes['aria-valuenow'] !== undefined) {
    screenReaderText += `, value ${attributes['aria-valuenow']}`;
    if (attributes['aria-valuemin'] && attributes['aria-valuemax']) {
      screenReaderText += ` of ${attributes['aria-valuemin']} to ${attributes['aria-valuemax']}`;
    }
  }
  
  return screenReaderText;
}

/**
 * Parse CSS style string into object
 * @param {string} styleString - CSS style string
 * @returns {Record<string, string>} - Parsed styles object
 */
function parseStyleString(styleString: string): Record<string, string> {
  const styles: Record<string, string> = {};

  if (!styleString) return styles;

  const declarations = styleString.split(';').filter(decl => decl.trim());

  for (const declaration of declarations) {
    const [property, value] = declaration.split(':').map(part => part.trim());
    if (property && value) {
      styles[property] = value;
    }
  }

  return styles;
}

/**
 * Detect event handlers from element attributes
 * @param {Record<string, string>} attributes - Element attributes
 * @returns {string[]} - Array of detected event handlers
 */
function detectEventHandlers(attributes: Record<string, string>): string[] {
  const eventHandlers: string[] = [];

  const eventAttributes = [
    'onclick', 'onchange', 'onsubmit', 'onload', 'onmouseover', 'onmouseout',
    'onfocus', 'onblur', 'onkeydown', 'onkeyup', 'onkeypress'
  ];

  for (const eventAttr of eventAttributes) {
    if (attributes[eventAttr]) {
      eventHandlers.push(eventAttr);
    }
  }

  // Check for modern event listeners (data attributes)
  for (const [key] of Object.entries(attributes)) {
    if (key.startsWith('data-on') || key.includes('listener')) {
      eventHandlers.push(key);
    }
  }

  return eventHandlers;
}

/**
 * Determine interaction type based on element properties
 * @param {string} tagName - Element tag name
 * @param {Record<string, string>} attributes - Element attributes
 * @returns {string | undefined} - Interaction type
 */
function determineInteractionType(
  tagName: string,
  attributes: Record<string, string>
): 'click' | 'input' | 'select' | 'drag' | 'hover' | undefined {

  // Input elements
  if (tagName === 'input' || tagName === 'textarea') {
    return 'input';
  }

  // Select elements
  if (tagName === 'select') {
    return 'select';
  }

  // Button elements or clickable elements
  if (tagName === 'button' || tagName === 'a' ||
    attributes.role === 'button' || attributes.onclick) {
    return 'click';
  }

  // Draggable elements
  if (attributes.draggable === 'true') {
    return 'drag';
  }

  // Elements with hover interactions
  if (attributes.onmouseover || attributes.onmouseout) {
    return 'hover';
  }

  // Default to click for interactive elements
  if (attributes.tabindex !== undefined || attributes['aria-label']) {
    return 'click';
  }

  return undefined;
}

/**
 *  This function will breakdown comprehenshive DOM
 *   
 * 
 * 
 * 
 * */
export async function simplifiedDOMDataExtraction(page: Page): Promise<any> {
  const opt = {
    includeHidden: true,
    includeIframes: true,
    includeShadowDOM: true,
    maxDepth: 10,
    timeout: 30000,
    enableCDPStrategy: true, // Enable CDP session strategy
    enableAccessibilityTreeStrategy: true, // Enable accessibility tree strategy
    generateWCAGCompliantSelectors: true, // Generate WCAG-compliant selectors
    debugMode: true, // Enable debug logging
  }
  const JsonData: any = await extractComprehensiveDOMData(page, opt);

  function simplifyElement(element: any) {
    return {
      tagName: element.tagName || undefined,
      id: element.attributes?.id || undefined,
      class: element.attributes?.class || undefined,
      text: element.textContent || undefined,
      role: element.accessibility?.role || undefined,
      name: element.accessibility?.name || undefined,
      isVisible: element.visual?.isVisible ?? undefined,
      boundingBlock: element.visual?.boundingBox ?? undefined,
      isInteractable: element.isInteractable ?? undefined,
      viewPoint: element.viewPoint || undefined,
      locators: Array.isArray(element.locatorCandidates)
        ? element.locatorCandidates
          .filter((c: any) => c && c.type && c.selector)
          .map((c: any) => ({
            type: c.type,
            selector: c.selector,
            confidence: c.confidence
          }))
        : [],
      parentHierarchy: Array.isArray(element.parentHierarchy) ? element.parentHierarchy.join(' > ') : undefined
    };
  }

  const simplifiedElements = JsonData.elements.map(simplifyElement);

  // Optionally, return or log the simplified elements
  //logger.info(simplifiedElements);
  return simplifiedElements;
}

export interface ParsedErrorInfo {
  action: string;
  selectorType: string;
  selector: string;
  summary: string;
  attributes?: Record<string, string>;
  role?: string;
  name?: string;
  text?: string; // Added text property
  partialText?: string; // Added partialText property
  id?: string; // Added id property
  class?: string; // Added class property
  tagName?: string; // Added tagName property
  xpath?: string; // Added xpath property
}
/**
 * Extract attributes and text from XPath using regex.
 */
function extractXPathAttributes(selector: string): Record<string, string> {
  const attrs: Record<string, string> = {};
  // [@attr="value"] or [@attr='value']
  const attrRegex = /@([\w-]+)\s*=\s*['"]([^'"]+)['"]/g;
  let match: RegExpExecArray | null;
  while ((match = attrRegex.exec(selector))) {
    attrs[match[1]] = match[2];
  }
  // [text()="value"]
  const textRegex = /text\(\)\s*=\s*['"]([^'"]+)['"]/g;
  while ((match = textRegex.exec(selector))) {
    attrs['text'] = match[1];
  }
  // [contains(@attr, "value")]
  const containsRegex = /contains\(@([\w-]+),\s*['"]([^'"]+)['"]\)/g;
  while ((match = containsRegex.exec(selector))) {
    attrs[match[1]] = match[2];
  }
  // [contains(text(), "value")]
  const containsTextRegex = /contains\(text\(\),\s*['"]([^'"]+)['"]\)/g;
  while ((match = containsTextRegex.exec(selector))) {
    attrs['partialText'] = match[1];
  }
  return attrs;
}
/**
 * Extract attributes from CSS selectors.
 */
function extractCSSAttributes(selector: string): Record<string, string> {
  const attrs: Record<string, string> = {};
  // [attr="value"]
  const cssAttrRegex = /\[([\w-]+)\s*=\s*['"]([^'"]+)['"]\]/g;
  let match: RegExpExecArray | null;
  while ((match = cssAttrRegex.exec(selector))) {
    attrs[match[1]] = match[2];
  }
  // #id and .class
  const idMatch = /#([\w-]+)/.exec(selector);
  if (idMatch) attrs['id'] = idMatch[1];
  const classMatch = /\.([\w-]+)/.exec(selector);
  if (classMatch) attrs['class'] = classMatch[1];
  return attrs;
}
function extractAction(errorLog: string): string {
  const actionMatch = /locator\.(\w+)/.exec(errorLog);
  if (actionMatch) return actionMatch[1];
  if (/waitForSelector/.test(errorLog)) return 'waitForSelector';
  if (/waitForXPath/.test(errorLog)) return 'waitForXPath';
  return 'unknown';
}
/*
*   Text match: How closely does the element's text or name match the expected value?
    Tag match: Does the tagName match what you expect?
    Role match: If you have a role, does it match?
    Parent hierarchy similarity: How many parent nodes match the expected hierarchy?
*/
export async function parsePlaywrightError(errorLog: string): Promise<ParsedErrorInfo | null> {
  const patterns: {
    regex: RegExp;
    selectorType: string;
    summary: (m: RegExpExecArray, selector: string, attrs: Record<string, string>) => string;
    attrExtractor?: (selector: string) => Record<string, string>;
    customFields?: (m: RegExpExecArray) => Partial<ParsedErrorInfo>;
  }[] = [
      // locator('...')
      {
        regex: /locator\.(\w+).*?waiting for locator\('([^']+)'\)/s,
        selectorType: 'locator',
        summary: (m, selector, attrs) =>
          `Unable to find element for locator: ${selector}` +
          (Object.keys(attrs).length ? ` with attributes ${JSON.stringify(attrs)}` : '') +
          ` (action: ${m[1]})`,
        attrExtractor: selector => {
          if (selector.startsWith('/') || selector.startsWith('(')) {
            return extractXPathAttributes(selector);
          } else {
            return extractCSSAttributes(selector);
          }
        },
      },
      // getByRole('role', { name: '...' })
      {
        regex: /waiting for getByRole\('([^']+)',\s*\{\s*name:\s*'([^']+)'\s*\}\)/s,
        selectorType: 'getByRole',
        summary: (m) => `Unable to find element with role '${m[1]}' and name '${m[2]}'`,
        customFields: (m) => ({ role: m[1], name: m[2] }),
      },
      // getByText('...')
      {
        regex: /waiting for getByText\('([^']+)'\)/s,
        selectorType: 'getByText',
        summary: (m) => `Unable to find element with text '${m[1]}'`,
        customFields: (m) => ({ text: m[1], name: m[1] }),
      },
      // getByLabel('...')
      {
        regex: /waiting for getByLabel\('([^']+)'\)/s,
        selectorType: 'getByLabel',
        summary: (m) => `Unable to find element with label '${m[1]}'`,
        customFields: (m) => ({ label: m[1], name: m[1] }),
      },
      // getByPlaceholder('...')
      {
        regex: /waiting for getByPlaceholder\('([^']+)'\)/s,
        selectorType: 'getByPlaceholder',
        summary: (m) => `Unable to find element with placeholder '${m[1]}'`,
        customFields: (m) => ({ placeholder: m[1], name: m[1] }),
      },
      // getByTestId('...')
      {
        regex: /waiting for getByTestId\('([^']+)'\)/s,
        selectorType: 'getByTestId',
        summary: (m) => `Unable to find element with test id '${m[1]}'`,
        customFields: (m) => ({ attributes: { testId: m[1] } }),
      },
      // CSS selector
      {
        regex: /waiting for locator\('([.#][^']+)'\)/s,
        selectorType: 'css',
        summary: (m, selector, attrs) =>
          `Unable to find element for CSS selector: ${selector}` +
          (Object.keys(attrs).length ? ` with attributes ${JSON.stringify(attrs)}` : ''),
        attrExtractor: extractCSSAttributes,
      },
      // XPath selector (generic, any axis)
      {
        regex: /locator\.(\w+).*?waiting for locator\((['"])([\s\S]+?)\2\)/s,
        selectorType: 'locator',
        summary: (m, selector, attrs) =>
          `Unable to find element for locator: ${selector}` +
          (Object.keys(attrs).length ? ` with attributes ${JSON.stringify(attrs)}` : '') +
          ` (action: ${m[1]})`,
        attrExtractor: selector => {
          const unescaped = selector.replace(/\\'/g, "'").replace(/\\"/g, '"');
          if (unescaped.startsWith('/') || unescaped.startsWith('(') || unescaped.startsWith('.')) {
            return extractXPathAttributes(unescaped);
          } else {
            return extractCSSAttributes(unescaped);
          }
        },
        customFields: (m) => {
          const selector = m[3].replace(/\\'/g, "'").replace(/\\"/g, '"');
          const isXPath = selector.startsWith('/') || selector.startsWith('(') || selector.startsWith('.');
          const result: Partial<ParsedErrorInfo> = {};
          if (isXPath) {
            result.xpath = selector;
          }
          return result;
        }
      },
      // page.waitForSelector
      {
        regex: /page\.waitForSelector: Timeout \d+ms exceeded.*?waiting for selector "([^"]+)"/s,
        selectorType: 'css',
        summary: (m, selector, attrs) =>
          `Unable to find element for selector: ${selector}` +
          (Object.keys(attrs).length ? ` with attributes ${JSON.stringify(attrs)}` : ''),
        attrExtractor: extractCSSAttributes,
      },
      // page.waitForXPath
      {
        regex: /page\.waitForXPath: Timeout \d+ms exceeded.*?waiting for XPath "([^"]+)"/s,
        selectorType: 'xpath',
        summary: (m, selector, attrs) =>
          `Unable to find element for XPath: ${selector}` +
          (Object.keys(attrs).length ? ` with attributes ${JSON.stringify(attrs)}` : ''),
        attrExtractor: extractXPathAttributes,
        customFields: (m) => {
          const selector = m[1];
          const attrs = extractXPathAttributes(selector);
          const result: Partial<ParsedErrorInfo> = {};
          if (attrs['text']) result.text = attrs['text'];
          if (attrs['partialText']) result.partialText = attrs['partialText'];
          if (attrs['id']) result.id = attrs['id'];
          if (attrs['class']) result.class = attrs['class'];
          if (attrs['name']) result.name = attrs['name'];
          return result;
        }
      },
    ];

  for (const pattern of patterns) {
    const match = pattern.regex.exec(errorLog);
    if (match) {
      const selector = match[2] || match[1] || '';
      const attrs = pattern.attrExtractor ? pattern.attrExtractor(selector) : {};
      const base: ParsedErrorInfo = {
        action: extractAction(errorLog),
        selectorType: pattern.selectorType,
        selector,
        summary: pattern.summary(match, selector, attrs),
        attributes: Object.keys(attrs).length ? attrs : undefined,
      };
      // Add custom fields if present
      if (pattern.customFields) {
        Object.assign(base, pattern.customFields(match));
      }

      // --- TagName extraction logic ---
      let tagName: string | undefined;
      // For XPath selectors
      if (selector.startsWith('//') || selector.startsWith('(')) {
        const tagMatch = selector.match(/^\/\/(?:[\w-]+:)?([\w*-]+)/);
        if (tagMatch && tagMatch[1] !== '*') tagName = tagMatch[1].toLowerCase();
      }
      // For CSS selectors
      else if (/^[a-zA-Z][\w-]*/.test(selector)) {
        const cssTagMatch = selector.match(/^([a-zA-Z][\w-]*)/);
        if (cssTagMatch) tagName = cssTagMatch[1].toLowerCase();
      }
      // For getByRole, getByText, etc.
      if (!tagName && pattern.selectorType === 'getByRole') {
        tagName = 'role';
      } else if (!tagName && pattern.selectorType === 'getByText') {
        tagName = 'text';
      }
      if (tagName) base.tagName = tagName;
      // --- End tagName extraction ---

      return base;
    }
  }

  return null;
}
function chunkSnapshot(data: any[], chunkSize: number) {
  // ✅ ULTRA-COMPRESSED: Compress DOM data before chunking to reduce tokens
  const compressedData = data.map(element => {
    // Keep only essential fields for healing based on simplifyElement structure
    return {
      tagName: element.tagName,
      id: element.id,
      class: element.class,
      text: element.text,
      role: element.role,
      name: element.name,
      isVisible: element.isVisible,
      isInteractable: element.isInteractable,
      // Include locators for selector generation
      locators: element.locators,
      // Include parent hierarchy for context
      parentHierarchy: element.parentHierarchy
    };
  });
  
  const chunks = [];
  for (let i = 0; i < compressedData.length; i += chunkSize) {
    chunks.push(compressedData.slice(i, i + chunkSize));
  }
  // Always return an array of chunks to ensure downstream code
  // consistently receives `any[]` representing a chunk of elements
  return chunks;
}

export async function healer(
  pageOrController: any,
  pageUrl: string,
  errorMsg: any,
  gherkinStep: any,
  framework: 'playwright' | 'testcafe' = 'playwright',
  options: {
    strategies?: Array<'cdp' | 'interaction' | 'history' | 'screenshot'>;
    serverEndpoint?: string;
    maxAttempts?: number;
    confidenceThreshold?: number;
  } = {}
): Promise<any> {
  const {
    strategies = ['cdp', 'screenshot'],
    serverEndpoint = 'http://10.0.0.244:5000/api/self-healing/ai-heal',
    maxAttempts = 3,
    confidenceThreshold = 0.6
  } = options;

  

  try {
    // Get healing strategies from environment variable
    const enabledStrategies = (process.env.HEALING_STRATEGIES || 'cdp,screenshot').split(',').map(s => s.trim());

    // Filter to only enabled strategies
    const availableStrategies = strategies.filter(strategy => enabledStrategies.includes(strategy));

    if (availableStrategies.length === 0) {
      logger.warn('⚠️ No enabled healing strategies found');
      return undefined;
    }

    // Execute strategies sequentially without complex synchronization for now
    let result: any = null;
    
    for (const strategy of availableStrategies) {

      
      try {
        switch (strategy) {
          case 'cdp':
            result = await cdpBasedHealing(pageOrController, pageUrl, errorMsg, gherkinStep, framework);
            break;
          case 'screenshot':
            result = await screenshotBasedHealing(pageOrController, pageUrl, errorMsg, gherkinStep, framework);
            break;
          case 'interaction':
            result = await interactionBasedHealing(pageOrController, pageUrl, errorMsg, gherkinStep, framework);
            break;
          case 'history':
            result = await historyBasedHealing(pageOrController, pageUrl, errorMsg, gherkinStep, framework);
            break;
          default:
            logger.warn(`⚠️ Unknown strategy: ${strategy}`);
            result = { success: false, error: `Unknown strategy: ${strategy}` };
        }
        
        // Check if we have a successful result and can terminate early
        if (result && result.success) {
          // Check confidence from different possible locations
          const confidence = result.healler?.locator?.confidence || 
                           result.healler?.confidence || 
                           result.confidence || 
                           0.8; // Default confidence for successful healing
          
          if (confidence >= confidenceThreshold) {
            // Log the healed locator and confidence for successful healing
            const healedLocator = result.healler?.locator?.recommended_locator || 
                                 result.healler?.action || 
                                 'Unknown locator';
            const strategy = result.strategy || 'unknown';
            logger.info(`🎯 Healing successful! Locator: ${healedLocator} | Confidence: ${(confidence * 100).toFixed(1)}% | Strategy: ${strategy}`);
            
            return result;
          } else {

          }
        }
        
      } catch (error) {
        logger.error(`❌ Strategy ${strategy} failed:`, error);
        result = { success: false, error: String(error) };
      }
    }

    // Check if we have a successful result
    if (result && result.success && result.healler?.locator?.confidence >= confidenceThreshold) {
      // Log the healed locator and confidence for successful healing
      const confidence = result.healler?.locator?.confidence || 0.8;
      const healedLocator = result.healler?.locator?.recommended_locator || 
                           result.healler?.action || 
                           'Unknown locator';
      const strategy = result.strategy || 'unknown';
      logger.info(`🎯 Healing successful! Locator: ${healedLocator} | Confidence: ${(confidence * 100).toFixed(1)}% | Strategy: ${strategy}`);
      
      return result;
    }

    logger.warn('⚠️ No healing strategy succeeded with sufficient confidence');
    return result || { success: false, error: 'All strategies failed' };

  } catch (error) {
    logger.error('❌ Error in enhanced healer:', error);
    return { success: false, error: String(error) };
  }
}
/**
 * Interface for healing strategy results
 */
interface HealingStrategyResult {
  success: boolean;
  healler: any; // Healer object containing healed selector and other details
  strategy: string;
  metadata?: Record<string, any>;
}

/**
 * function to call healing agents over agentic api
 */
async function cdpserverSideLLMHealing(
  chunkedDOM: any,
  errorMsg: string,
  gherkinStep: string,
  framework: 'playwright' | 'testcafe',
  serverEndpoint: string,
  options: { testName?: string; runId?: string; caseId?: string } = {}
): Promise<string | undefined> {
  try {

    const response = await fetch(serverEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        errorMessage: errorMsg,
        gherkinStep: gherkinStep,
        framework: framework,
        domChunk: chunkedDOM,
        testName: 'healing-test', // Placeholder for test name
        runId: 'run-12345', // Placeholder for run ID
        caseId: 'case-67890', // Placeholder for case ID
      })
    });
    if (!response.ok) {
      logger.error('Server-side healing failed:', response.statusText);
      return undefined;
    }
    const result = await response.json();
    if (result.success && result.suggestions && result.suggestions.length > 0) {
      // Assuming the first suggestion is the best one
      
      return result;
    } else {
      logger.warn('Server-side healing did not return a valid step:', result);
      return undefined;
    }
  } catch (error) {
    logger.error('Error during server-side LLM healing:', error);
    return undefined;
  }
}

/**
 * Strategy 0: Interaction-based healing strategy
 */
async function interactionBasedHealing(
  pageOrController: any,
  pageUrl: string,
  errorMsg: string,
  gherkinStep: string,
  framework: 'playwright' | 'testcafe'
): Promise<HealingStrategyResult | null> {
  try {


    // This would implement interaction-based healing
    // For now, return a placeholder implementation

    
    return {
      success: false,
      healler: 'Interaction healing not implemented',
      strategy: 'interaction'
    };
  } catch (error) {
    logger.warn('Interaction healing failed:', error);
    return {
      success: false,
      healler: String(error),
      strategy: 'interaction'
    };
  }
}

/**
 * Strategy 0.5: History-based healing strategy
 */
async function historyBasedHealing(
  pageOrController: any,
  pageUrl: string,
  errorMsg: string,
  gherkinStep: string,
  framework: 'playwright' | 'testcafe'
): Promise<HealingStrategyResult | null> {
  try {


    // This would implement history-based healing
    // For now, return a placeholder implementation

    
    return {
      success: false,
      healler: 'History healing not implemented',
      strategy: 'history'
    };
  } catch (error) {
    logger.warn('History healing failed:', error);
    return {
      success: false,
      healler: String(error),
      strategy: 'history'
    };
  }
}

/**
 * Strategy 1: CDP Session Based Healing
 * Enhanced to support both Playwright and TestCafe
 */
async function cdpBasedHealing(
  pageOrController: any,
  pageUrl: string,
  errorMsg: string,
  gherkinStep: string,
  framework: 'playwright' | 'testcafe'
): Promise<HealingStrategyResult | null> {
  try {


    let domAnalysis: any;

    if (framework === 'playwright') {
      // Use existing Playwright CDP extraction
      domAnalysis = await extractComprehensiveDOMData(pageOrController, {
        enableCDPStrategy: true,
        enableAccessibilityTreeStrategy: true,
        generateWCAGCompliantSelectors: true,
        debugMode: false
      });
    } else if (framework === 'testcafe') {
      // TestCafe CDP extraction using native CDP session
      // Reference: https://testcafe.io/documentation/404913/reference/test-api/testcontroller/getcurrentcdpsession
      
      domAnalysis = await extractTestCafeCDPData(pageOrController,{
        enableCDPStrategy: true,
        enableAccessibilityTreeStrategy: true,
        generateWCAGCompliantSelectors: true,
        debugMode: false}
      );
    }
    const skiewdHealer = await healLocator(errorMsg, gherkinStep, domAnalysis);
    // ✅ OPTIMIZED: Use smaller chunk size for better token efficiency
    const chunkedDOM = chunkSnapshot(skiewdHealer, Number(process.env.HEALING_CHUNK_SIZE) || 5);

    try {
      let foundHealer = false;
      const chunkResponses: any[] = [];
                  // Process chunks sequentially to prevent race conditions
            // Use environment variables for batch configuration
            const BATCH_SIZE = Number(process.env.LLM_MAX_CHUNKS) || 10;
            const MAX_CONCURRENT_CHUNKS = Number(process.env.LLM_MAX_CONCURRENT_CHUNKS) || 5;
            
            logger.info(`�� Processing ${chunkedDOM.length} chunks in batches of ${BATCH_SIZE} with max ${MAX_CONCURRENT_CHUNKS} concurrent per batch`);
            
            // Process chunks in batches - wait for each batch to complete before next
            for (let i = 0; i < chunkedDOM.length && !foundHealer; i += BATCH_SIZE) {
              const currentBatch = chunkedDOM.slice(i, i + BATCH_SIZE);
              const batchNumber = Math.floor(i / BATCH_SIZE) + 1;
              const totalBatches = Math.ceil(chunkedDOM.length / BATCH_SIZE);
              

              
              // Process ALL chunks in this batch in parallel with concurrency limit
              const batchPromises = currentBatch.map(async (chunk, batchIndex) => {
                const chunkIndex = i + batchIndex;

                
                try {
                  const chunkPrompt = adkClient.buildCDPPromptForChunk(pageOrController, pageUrl, errorMsg, gherkinStep, framework, chunk, chunkedDOM.length, chunkIndex);
                  
                  let chunkResponse: any;
                  let currentChunkResponseText: string = '';
                  if (process.env.USE_GCP_HEALING === 'true') {
                    let retryCount = 0;
                    const MAX_RETRIES = 2;
                    currentChunkResponseText = await adkClient.callGeminiModel(chunkPrompt);
                    
                    while (retryCount <= MAX_RETRIES) {
                      try {
                        chunkResponse = await adkClient.parseHealingResponse(currentChunkResponseText, 'cdp');
                        break;
                      } catch (parseError) {
                        logger.warn(`JSON parsing failed for chunk ${chunkIndex + 1} (attempt ${retryCount + 1}/${MAX_RETRIES + 1}):`, parseError);
                        logger.warn('Unparseable response:', currentChunkResponseText);
      
                        if (retryCount < MAX_RETRIES) {
                          const fixPrompt = adkClient.buildFixJsonPrompt(currentChunkResponseText, parseError);
                          currentChunkResponseText = await adkClient.callGeminiModel(fixPrompt);
                          retryCount++;
                        } else {
                          logger.error(`All JSON parsing attempts failed for chunk ${chunkIndex + 1}. Continuing with next chunk.`);
                          chunkResponse = { success: false, suggestions: [], reasoning: 'Failed to parse LLM response after multiple retries.' };
                          break;
                        }
                      }
                    }
                  } else {
                    chunkResponse = await cdpserverSideLLMHealing(chunk, errorMsg, gherkinStep, framework, 'http://10.0.0.244:5000/api/self-healing/ai-heal');
                  }
                  return { chunkIndex, chunkResponse, chunkPrompt, currentChunkResponseText };
                } catch (error) {
                  logger.warn(`Error processing chunk ${chunkIndex + 1}:`, error);
                  return { chunkIndex, chunkResponse: { success: false, error, chunkIndex }, chunkPrompt: '', currentChunkResponseText: '' };
                }
              });
              
              // Process chunks in parallel with concurrency control
              // This ensures the entire batch completes before moving to the next
              const batchResults = [];
              for (let j = 0; j < batchPromises.length; j += MAX_CONCURRENT_CHUNKS) {
                const concurrentBatch = batchPromises.slice(j, j + MAX_CONCURRENT_CHUNKS);

                
                const concurrentResults = await Promise.all(concurrentBatch);
                batchResults.push(...concurrentResults);
              }
              
              // Now check ALL results from this completed batch

              
              for (const result of batchResults) {
                const { chunkIndex, chunkResponse, chunkPrompt, currentChunkResponseText } = result;
                
                if (chunkResponse?.suggestions?.length > 0) {

                  const healed = await testHealedSelector(pageOrController, chunkResponse.suggestions, framework);
                  
                  if (healed.success) {
                    // Log successful healing data to JSONL (only if TRAINING_DATA=true)
                    const healedLocator = healed.locator || 'Unknown locator';
                    jsonlLogger.logHealingData(chunkPrompt, currentChunkResponseText, healedLocator);

                    foundHealer = true;
                    return { success: true, healler: healed, strategy: 'cdp' };
                  } else {
                    logger.warn(`Healed selector not found in chunk ${chunkIndex + 1}`);
                    chunkResponses.push(chunkResponse);
                  }
                } else {
                  logger.warn(`No valid suggestions from chunk ${chunkIndex + 1}`);
                  chunkResponses.push({
                    success: false,
                    suggestions: [],
                    reasoning: `No suggestions from chunk ${chunkIndex + 1}`
                  });
                }
              }
              
              // Batch is completely finished - log summary
              if (foundHealer) {
    
              } else {

              }
              
              // If we found a healer, break out of the batch loop
              if (foundHealer) break;
            }
      if (chunkResponses.length === 0 && chunkedDOM.length > 0) {
        logger.warn('No responses were collected from processed chunks.');
        return { success: false, healler: 'No responses from processed chunks', strategy: 'cdp' };
      }


      const aggregatedResponse = adkClient.aggregateChunkResponses(chunkResponses, 'cdp');

      if (aggregatedResponse && aggregatedResponse.suggestions && aggregatedResponse.suggestions.length > 0) {

        // testHealedSelector expects an array of suggestions
        const healed = await testHealedSelector(pageOrController, aggregatedResponse.suggestions, framework);
        if (healed.success) {
  
          return { success: true, healler: healed, strategy: 'cdp-aggregated' };
        } else {
          logger.warn('No valid healed selector found in aggregated chunks.');
          return { success: false, healler: healed, strategy: 'cdp-aggregated-failed' };
        }
      } else {
        logger.warn('No valid locators found after aggregating chunk responses.');
        return { success: false, healler: 'Not Found after aggregation', strategy: 'cdp' };
      }
    } catch (e) {
      logger.error('Error processing DOM chunks in cdpBasedHealing:', e);
      return { success: false, healler: String(e), strategy: 'cdp-error' };
    }
  } catch (error) {
    logger.warn('CDP healing failed:', error);
    return { success: false, healler: 'No Element Found to heal', strategy: 'cdp' };
  }
}

// function applyLocator(page: any, suggestion: any, framework: 'playwright' | 'testcafe'): any {
//   if (framework === 'playwright') {
//     switch (suggestion.strategy) {
//       case 'getByRole': {
//         try{
//           const obj = JSON.parse(suggestion.recommended_locator);
//           if (obj.role && obj.name) {
//             return page.getByRole(`role=${obj.role}[name='${obj.name}']`);
//           }
//         }catch {
//         }
//         return page.locator(suggestion.recommended_locator);
//       }
//       case 'getByText':
//         return page.getByText(new RegExp(suggestion.recommended_locator));
//       case 'getByLabel':
//         return page.getByLabel(suggestion.recommended_locator);
//       case 'getByPlaceholder':
//         return page.getByPlaceholder(suggestion.recommended_locator);
//       case 'getByTestId':
//         return page.getByTestId(suggestion.recommended_locator);
//       case 'css':
//       case 'xpath':
//       case 'selector':
//         return page.locator(suggestion.recommended_locator);
//       case 'role':
//         return page.locator(`[role="${suggestion.recommended_locator}"]`);
//       default:
//         throw new Error(`Unsupported strategy: ${suggestion.recommended_locator}`);
//     }
//   }

//   if (framework === 'testcafe') {
//     switch (suggestion.strategy) {
//       case 'getByRole':
//       case 'role': {
//         const { role, name } = JSON.parse(suggestion.recommended_locator);
//         return Selector(`[role="${role}"]`).withText(name);
//       }
//       case 'getByText':
//         return Selector(suggestion.recommended_tagName).withText(suggestion.recommended_locator);
//       case 'getByLabel':
//         return Selector('label').withText(suggestion.recommended_locator);
//       case 'getByPlaceholder':
//         return Selector(`[placeholder="${suggestion.recommended_locator}"]`);
//       case 'getByTestId':
//         return Selector(`[data-testid="${suggestion.recommended_locator}"]`);
//       case 'css':
//       case 'xpath':
//       case 'selector':
//         return Selector(suggestion.recommended_locator);
//       default:
//         throw new Error(`Unsupported strategy: ${suggestion.strategy}`);
//     }
//   }

//   throw new Error(`Unsupported framework: ${framework}`);
// }
function cleanLocator(raw: string): string {
  let cleaned = raw.trim();

  // Remove Playwright wrapper locator('...')
  if (cleaned.startsWith('locator(')) {
    cleaned = cleaned.replace(/^locator\((['"`])/, '').replace(/(['"`])\)$/, '');
  }

  // Remove playwright XPath prefix if present
  if (cleaned.startsWith('xpath=')) {
    cleaned = cleaned.replace(/^xpath=/, '');
  }

  // Remove CSS wrapper css('...')
  if (cleaned.startsWith('css(') && cleaned.endsWith(')')) {
    cleaned = cleaned.slice(4, -1);
  }

  return cleaned;
}
function preprocessLocatorString(locatorString: string): string {
  // Handle malformed CSS prefix with parentheses
  if (locatorString.startsWith('css(') && locatorString.endsWith(')')) {
    const result = locatorString.slice(4, -1);
    logger.debug(`🔧 CSS wrapper removed: "${locatorString}" -> "${result}"`);
    return result;
  }
  // Handle malformed XPath prefix with parentheses
  if (locatorString.startsWith('xpath(') && locatorString.endsWith(')')) {
    return locatorString.slice(6, -1);
  }
  // Handle ID prefix
  if (locatorString.startsWith('id=')) {
    return '#' + locatorString.slice(3);
  }
  // Handle name prefix
  if (locatorString.startsWith('name=')) {
    return '[name="' + locatorString.slice(5) + '"]';
  }
  // Handle class prefix
  if (locatorString.startsWith('class=')) {
    return '.' + locatorString.slice(6);
  }
  // Handle linkText prefix
  if (locatorString.startsWith('linkText=')) {
    const text = locatorString.slice(9);
    return generatePlaywrightLocatorString('getByRole', { role: 'link', name: text });
  }
  // Handle partialLinkText prefix
  if (locatorString.startsWith('partialLinkText=')) {
    const text = locatorString.slice(16);
    return generatePlaywrightLocatorString('getByRole', { role: 'link', name: text });
  }
  // Handle tagName prefix
  if (locatorString.startsWith('tagName=')) {
    return locatorString.slice(8);
  }
  // Handle getByAttribute
  if (locatorString.match(/(?:(page\.)?)getByAttribute\('([^']*)',\s*'([^']*)'\)/)) {
    return locatorString.replace(
      /(?:(page\.)?)getByAttribute\('([^']*)',\s*'([^']*)'\)/g,
      (match: string, p1: string, p2: string, p3: string) => {
        const pagePrefix = p1 || '';
        return `${pagePrefix}locator('[${p2}="${p3}"]')`;
      }
    );
  }
  // Return unchanged if no prefix matches
  return locatorString;
}
export async function resolveLocator(
  page: Page,
  suggestion: any,
  waitForVisible: boolean = true,
  framework: 'playwright' | 'testcafe'
): Promise<any> {
  if (framework === 'playwright') {
    let locator: Locator;
    try {
      switch (suggestion.strategy) {
        case 'getByRole': {
          // Extract role and name from the recommended_locator string
          const match = suggestion.recommended_locator.match(/getByRole\(\s*'([^']+)'\s*,\s*\{\s*name:\s*'([^']+)'/);
          if (match) {
            locator = page.getByRole(match[1], { name: match[2] });
          } else {
            // Try to extract just the role without name
            const roleMatch = suggestion.recommended_locator.match(/getByRole\(\s*'([^']+)'\s*\)/);
            if (roleMatch) {
              locator = page.getByRole(roleMatch[1]);
            }
          }
          break;
        }
        case 'getByText': {
          // Extract the text content from the recommended_locator string
          const textMatch = suggestion.recommended_locator.match(/getByText\('([^']*)'\)/);
          if (textMatch) {
            locator = page.getByText(textMatch[1]);
          } else {
            // Fallback: try to use as direct text
            locator = page.getByText(suggestion.recommended_locator);
          }
          break;
        }
        case 'getByLabel': {
          // Extract the label content from the recommended_locator string
          const labelMatch = suggestion.recommended_locator.match(/getByLabel\('([^']*)'\)/);
          if (labelMatch) {
            locator = page.getByLabel(labelMatch[1]);
          } else {
            // Fallback: try to use as direct label
            locator = page.getByLabel(suggestion.recommended_locator);
          }
          break;
        }
        case 'getByPlaceholder': {
          locator = page.getByPlaceholder(suggestion.recommended_locator);
          break;
        }
        case 'getByAltText': {
          locator = page.getByAltText(suggestion.recommended_locator);
          break;
        }
        case 'getByTitle': {
          locator = page.getByTitle(suggestion.recommended_locator);
          break;
        }
        case 'getByTestId': {
          // Extract the test ID from the recommended_locator string
          const testIdMatch = suggestion.recommended_locator.match(/getByTestId\('([^']*)'\)/);
          if (testIdMatch) {
            locator = page.getByTestId(testIdMatch[1]);
          } else {
            // Fallback: try to use as direct test ID
            locator = page.getByTestId(suggestion.recommended_locator);
          }
          break;
        }
        case 'xpath': {
          const cleaned = cleanLocator(suggestion.recommended_locator);
          locator = page.locator(cleaned);
          break;
        }
        case 'css':
        case 'text':
        case 'tag': {
            locator = page.locator(preprocessLocatorString(suggestion.recommended_locator));
            break;
        }
        case 'id': {
            locator = page.locator(`#${cleanLocator(suggestion.recommended_locator)}`);
            break;
        }
          
        case 'class': {
            locator = page.locator(`.${cleanLocator(suggestion.recommended_locator)}`);
            break;
        }
        case 'nth': {
          const [baseSelector, nthIndex] = suggestion.recommended_locator.split('::nth=');
          locator = page.locator(baseSelector).nth(parseInt(nthIndex, 10));
          break;
        }
        default: {
          throw new Error(`Unsupported locator type: ${suggestion.locator_type}`);
        }
      }
      // Return the created locator
      return locator;
    }
    catch (error) {
      console.error(`❌ Failed to use healed locator: ${suggestion.recommended_locator}`, error);
      throw error;
    }
  } else if (framework === 'testcafe') {
    try {
      switch (suggestion.strategy) {
        case 'getByRole': {
          const match = suggestion.recommended_locator.match(/getByRole\('(.*?)',\s*\{\s*name:\s*'(.*?)'(,\s*exact:\s*true)?\s*\}\)/);
          if (match) {
            const role = match[1];
            const name = match[2];
            return Selector(`[role="${role}"]`).withText(name);
          }
          break;
        }
        case 'getByText': {
          const match = suggestion.recommended_locator.match(/getByText\('(.*?)'(,\s*\{\s*exact:\s*true\s*\})?\)/);
          if (match) {
            return Selector('*').withText(match[1]);
          }
          break;
        }
        case 'getByTestId': {
          const match = suggestion.recommended_locator.match(/getByTestId\('(.*?)'\)/);
          if (match) {
            return Selector(`[data-testid="${match[1]}"]`);
          }
          break;
        }
        case 'css':
          return Selector(suggestion.recommended_locator);
        case 'text':
          return Selector('*').withText(suggestion.recommended_locator.replace(/^text=['"]?(.*?)['"]?$/, '$1'));
        case 'id':
          return Selector(`#${suggestion.recommended_locator}`);
        case 'xpath':
          return Selector(suggestion.recommended_locator);
      }
    } catch (e) {
      console.warn('TestCafe selector resolution failed:', e);
    }
    return null;
  }
}
function getLocator(framework:any, context:any, locatorString:any) {
  if (typeof locatorString !== 'string') {
    throw new Error('locatorString must be a string');
  }

  try {
    if (framework === 'playwright') {
      // Preprocess for custom methods
      let processedString = preprocessLocatorString(locatorString);
      logger.debug(`🔧 Processing locator: "${locatorString}" -> "${processedString}"`);
      // Validate context as Playwright page object
      if (typeof context.getByRole !== 'function') {
        throw new Error('Context does not appear to be a Playwright page object');
      }
      if (processedString.includes(' >> ')) {
        // Handle chained locators
        const [basePart, chainedPart] = processedString.split(' >> ');
        // Create baseLocator from basePart
        let baseAdjusted = basePart.trim();
        if (!baseAdjusted.startsWith('page.')) {
          const match = baseAdjusted.match(/^(\w+)\(/);
          if (match && typeof context[match[1]] === 'function') {
            baseAdjusted = `page.${baseAdjusted}`;
          } else {
            baseAdjusted = `page.locator(${JSON.stringify(baseAdjusted)})`;
          }
        }
        const baseFunc = new Function('page', `return ${baseAdjusted}`);
        const baseLocator = baseFunc(context);
        // Chain the second part
        const func = new Function('locator', `return locator.${chainedPart}`);
        return func(baseLocator);
      } else {
        // Single part
        let adjustedString = processedString.trim();
        
                        // Handle XPath selectors properly (both formats)
                if (adjustedString.startsWith('xpath:')) {
                  const xpathExpression = adjustedString.replace('xpath:', '');
                  logger.debug(`Creating XPath locator for: ${xpathExpression}`);
                  return context.locator(`xpath=${xpathExpression}`);
                }
                if (adjustedString.startsWith('//') || adjustedString.startsWith('./')) {
                  logger.debug(`Creating XPath locator for: ${adjustedString}`);
                  return context.locator(`xpath=${adjustedString}`);
                }
        
        // Handle getBy* methods
        if (adjustedString.startsWith('getBy')) {
          const match = adjustedString.match(/^(\w+)\((.*)\)$/);
          if (match && match.length >= 3 && typeof context[match[1]] === 'function') {
            try {
              const [_, method, argsString] = match;
              
              // Handle complex arguments like getByRole('link', { name: 'About CNA' })
              if (argsString.includes('{') && argsString.includes('}')) {
                // Find the first argument (string)
                const firstArgMatch = argsString.match(/^'([^']+)'|^"([^"]+)"/);
                if (firstArgMatch) {
                  const firstArg = firstArgMatch[1] || firstArgMatch[2];
                  
                  // Find the object argument
                  const objectMatch = argsString.match(/\{([^}]+)\}/);
                  if (objectMatch) {
                    const objectStr = `{${objectMatch[1]}}`;
                    try {
                      // Clean up the object string for JSON parsing
                      const cleanObjectStr = objectStr
                        .replace(/'/g, '"') // Replace single quotes with double quotes
                        .replace(/(\w+):/g, '"$1":'); // Ensure property names are quoted
                      
                      const parsedObject = JSON.parse(cleanObjectStr);
                      return context[method](firstArg, parsedObject);
                    } catch (objectParseError) {
                      logger.warn(`Failed to parse object argument: ${objectStr}`, objectParseError);
                      // Fallback to string-only argument
                      return context[method](firstArg);
                    }
                  }
                }
              }
              
              // Handle simple string arguments
              const cleanArgs = argsString.replace(/'/g, '').replace(/"/g, ''); // Remove quotes
              return context[method](cleanArgs);
            } catch (parseError) {
              logger.warn(`Failed to parse getBy* arguments: ${match ? match[2] : 'unknown'}`, parseError);
              // Fallback to generic locator
              return context.locator(adjustedString);
            }
          }
        }
        
        // Handle other locator types
        if (!adjustedString.startsWith('page.')) {
          const match = adjustedString.match(/^(\w+)\(/);
          if (match && match[1] && typeof context[match[1]] === 'function') {
            adjustedString = `page.${adjustedString}`;
          } else {
            adjustedString = `page.locator(${JSON.stringify(adjustedString)})`;
          }
        }
        
        // Use safer evaluation for complex locators
        try {
          const func = new Function('page', `return ${adjustedString}`);
          return func(context);
        } catch (evalError) {
          logger.warn(`Failed to evaluate locator: ${adjustedString}`, evalError);
          // Fallback to direct locator creation
          return context.locator(adjustedString);
        }
      }
    } else if (framework === 'testcafe') {
      // Validate context as TestCafe Selector function
      if (typeof context !== 'function') {
        throw new Error('Context must be the TestCafe Selector function');
      }
      let adjustedString;
      if (locatorString.trim().startsWith('Selector')) {
        adjustedString = locatorString.replace(/\bSelector\b/g, 'context');
      } else {
        adjustedString = `context(${JSON.stringify(locatorString)})`;
      }
      const func = new Function('context', `return ${adjustedString}`);
      return func(context);
    } else {
      throw new Error('Unsupported framework');
    }
  } catch (error) {
    logger.warn(`Locator conversion failed for: "${locatorString}"`, error);
    throw new Error(`Failed to convert locator string: ${error instanceof Error ? error.message : String(error)}`);
  }
}
  async function applyLocator(page: any, suggestion: any, framework: 'playwright' | 'testcafe'): Promise<any> {
    try {
      if (framework === 'playwright') {
        // Validate that we have a valid recommended_locator
        if (!suggestion.recommended_locator || typeof suggestion.recommended_locator !== 'string') {
          logger.warn(`Invalid recommended_locator: ${JSON.stringify(suggestion.recommended_locator)}`);
          return null;
        }
        
        const locator = await getLocator(framework, page, suggestion.recommended_locator);
        if (locator) {
          return locator;
        }else if(suggestion.strategy?.startsWith('getBy')) {
          // Parse getBy* methods properly
          const methodMatch = suggestion.recommended_locator.match(/^(getBy\w+)\((.*)\)$/);
          if (methodMatch && methodMatch.length >= 3) {
            const [_, method, args] = methodMatch;
            try {
              // Parse the arguments safely
              let parsedArgs;
              if (args.includes('{') && args.includes('}')) {
                // Handle object arguments like { name: 'Login' }
                const cleanArgs = args.replace(/'/g, '"'); // Replace single quotes with double quotes
                parsedArgs = JSON.parse(cleanArgs);
                return page[method](parsedArgs);
              } else {
                // Handle simple string arguments
                const cleanArgs = args.replace(/'/g, '').replace(/"/g, ''); // Remove quotes
                return page[method](cleanArgs);
              }
            } catch (parseError) {
              logger.warn(`Failed to parse getBy* arguments: ${args}`, parseError);
              // Fallback to generic locator
              return page.locator(suggestion.recommended_locator);
            }
          }
        }
        
        // Handle XPath selectors properly for Playwright (both formats)
        if (suggestion.recommended_locator.startsWith('xpath:')) {
          const xpathExpression = suggestion.recommended_locator.replace('xpath:', '');
          logger.debug(`Creating XPath locator for: ${xpathExpression}`);
          return page.locator(`xpath=${xpathExpression}`);
        }
        if (suggestion.recommended_locator.startsWith('//') || suggestion.recommended_locator.startsWith('./')) {
          logger.debug(`Creating XPath locator for: ${suggestion.recommended_locator}`);
          return page.locator(`xpath=${suggestion.recommended_locator}`);
        }
        
        // Handle CSS selectors and other types
        return page.locator(preprocessLocatorString(suggestion.recommended_locator));
      } else if (framework === 'testcafe'){
        try {
          // Import TestCafe dependencies
          const { Selector, ClientFunction } = require('testcafe');
          
          if (suggestion.strategy === 'xpath') {
            const clientFunction = ClientFunction(xpath => {
              const iterator = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
              return iterator.singleNodeValue;
            });
            return clientFunction(suggestion.recommended_locator);
          }
          
          // Try to resolve using the existing resolveLocator function
          const locator = await resolveLocator(page, suggestion, true, 'testcafe');
          if (locator) {
            return locator;
          } else {
            // Fallback to creating a Selector from the recommended_locator
            return Selector(suggestion.recommended_locator);
          }
        } catch (importError) {
          logger.warn('Failed to import TestCafe dependencies:', importError);
          // Fallback to basic selector creation
          try {
            const { Selector } = require('testcafe');
            return Selector(suggestion.recommended_locator);
          } catch (fallbackError) {
            logger.warn('TestCafe Selector fallback also failed:', fallbackError);
            return null;
          }
        }
      }
    } catch (error) {
      logger.warn(`Failed to create locator: ${error}`);
      // Return a null locator that will fail gracefully
      if (framework === 'playwright') {
        return page.locator('null');
      } else if (framework === 'testcafe') {
        try {
          const { Selector } = require('testcafe');
          return Selector('null');
        } catch (importError) {
          logger.warn('Failed to import TestCafe Selector for fallback:', importError);
          return null;
        }
      }
      return null;
    }
  }
  async function testHealedSelector(page: any, healedSuggestions: any, framework: 'playwright' | 'testcafe'): Promise<{ success: boolean, locator: any, action: any }> {
    // Validate that we have valid selector suggestions before testing
    if (!healedSuggestions || healedSuggestions.length === 0) {
      logger.warn('No valid selector suggestions found for healing');
      return { success: false, locator: 'No valid selectors', action: null };
    }
    
    // Filter out invalid selectors (navigation commands, invalid CSS, etc.)
    const validSuggestions = healedSuggestions.filter(suggestion => {
      const selector = suggestion.selector || suggestion.recommended_locator;
      if (!selector || typeof selector !== 'string') return false;
      
      // Reject navigation commands
      if (selector.includes('page.goto') || selector.includes('navigate') || selector.includes('waitUntil')) {
        logger.debug(`Rejecting navigation command as selector: ${selector}`);
        return false;
      }
      
      // Reject invalid CSS selectors
      if (selector.includes('N/A') || selector.includes('undefined') || selector.includes('null')) {
        logger.debug(`Rejecting invalid selector: ${selector}`);
        return false;
      }
      
      // Basic selector validation for CSS, XPath, and Playwright locators
      try {
                        // XPath selectors (both formats)
                if (selector.startsWith('xpath:') || selector.startsWith('//') || selector.startsWith('./')) {
                  logger.debug(`Validating XPath selector: ${selector}`);
                  return true;
                }
        
        // CSS selectors
        if (selector.startsWith('#') || selector.startsWith('.') || selector.startsWith('[') || 
            selector.includes('css=') || selector.includes('text=')) {
          logger.debug(`Validating CSS selector: ${selector}`);
          return true;
        }
        
        // Playwright locators
        if (selector.includes('getBy') || selector.includes('locator')) {
          logger.debug(`Validating Playwright locator: ${selector}`);
          return true;
        }
        
        // Reject if it looks like a navigation command or invalid selector
        if (selector.includes('(') && selector.includes(')') && 
            (selector.includes('goto') || selector.includes('wait') || selector.includes('timeout'))) {
          logger.debug(`Rejecting function call as selector: ${selector}`);
          return false;
        }
        
        // Allow other valid patterns
        return true;
      } catch (validationError) {
        logger.debug(`Selector validation failed for: ${selector}`, validationError);
        return false;
      }
    });
    
    if (validSuggestions.length === 0) {
      logger.warn('All selector suggestions were invalid after filtering');
      return { success: false, locator: 'No valid selectors after filtering', action: null };
    }
    
    logger.debug(`Filtered ${healedSuggestions.length} suggestions down to ${validSuggestions.length} valid selectors`);
    
    // Use only valid suggestions for testing
    for (const suggestion of validSuggestions) {
      try {
        // Use applyLocator helper to get the appropriate locator based on framework
        const locator = await applyLocator(page, suggestion, framework);

        if (framework === 'playwright') {
          const count = await locator.count();
          if (count === 1) {
            return { success: true, locator: suggestion, action: locator }; // Unique element found
          } else if (count > 1) {
            logger.warn(`Locator "${suggestion.recommended_locator}" matched multiple elements (${count}). Using first element.`);

            // Use the first element when multiple elements are found
            const firstElement = locator.first();
            return {
              success: true,
              locator: {
                ...suggestion,
                recommended_locator: `${suggestion.recommended_locator}.first()`
              },
              action: firstElement // Return the first element
            };
          }
        } else if (framework === 'testcafe') {
          const element = locator; // For TestCafe, locator is already a Selector
          
          // Check if locator is null (failed to create)
          if (!element) {
            logger.warn(`Failed to create TestCafe locator for: ${suggestion.recommended_locator}`);
            continue;
          }
          
          if (element && typeof element.count === 'function') {
            try {
              const count = await element.count();
              if (count === 1) {
                return { success: true, locator: suggestion, action: element }; // Unique element found
              } else if (count > 1) {
                logger.warn(`Locator "${suggestion.recommended_locator}" matched multiple elements (${count}). Using first element.`);
                
                // Use the first element when multiple elements are found
                const firstElement = element.nth(0);
                return {
                  success: true,
                  locator: {
                    ...suggestion,
                    recommended_locator: `${suggestion.recommended_locator} >> nth=0`
                  },
                  action: firstElement // Return the first element
                };
              }
            } catch (countError) {
              logger.warn(`Failed to get count for TestCafe locator: ${suggestion.recommended_locator}`, countError);
              continue;
            }
          } else if (element) {
            return { success: true, locator: suggestion, action: element }; // Single element found
          }
        }
      } catch (error) {
        logger.warn(`Testing healed selector failed: ${suggestion.selector || suggestion.recommended_locator}`, error);
      }
    }
    


    return { success: false, locator: 'Not found in the current Chunk', action: null };
  }
  /**
   * Strategy 2: Interaction-Based Healing
   * Recovers elements using recorded user behavior history
   */
  // async function interactionBasedHealing(
  //   pageOrController: any,
  //   errorMsg: string,
  //   gherkinStep: string,
  //   framework: 'playwright' | 'testcafe'
  // ): Promise< any > {
  //   try {
  //     logger.info('🎯 Analyzing interaction history...');

  //     // Get recent successful interactions from storage
  //     const recentInteractions = await getRecentSuccessfulInteractions(gherkinStep);

  //     if (recentInteractions.length === 0) {
  //       //return { success: false, confidence: 0, strategy: 'interaction' };
  //     }

  //     // Try last known successful step
  //     const lastSuccessful = recentInteractions[0];
  //     if (lastSuccessful.selector) {
  //       const testResult = await testSelector(pageOrController, lastSuccessful.selector, framework);
  //       if (testResult.success) {
  //         const healedStep = await convertLocatorToStep(
  //           lastSuccessful.selector,
  //           lastSuccessful.selectorType,
  //           gherkinStep,
  //           framework
  //         );

  //     //     return {
  //     //       success: true,
  //     //       //healedStep,
  //     //       //confidence: 0.85,
  //     //       strategy: 'interaction-last-successful',
  //     //       metadata: { originalInteraction: lastSuccessful }
  //     //     };
  //         return {
  //           success: true,
  //           healler:healedStep,
  //           strategy: 'interaction-last-successful',
  //           metadata: { originalInteraction: lastSuccessful }
  //         };
  //       }
  //     // Try semantic replay using interaction patterns
  //     const semanticResult = await semanticInteractionReplay(
  //       pageOrController,
  //       recentInteractions,
  //       gherkinStep,
  //       framework
  //     );

  //     if (semanticResult && semanticResult.success) {
  //       return semanticResult;
  //     }

  //     // Try keyboard/mouse navigation patterns
  //     const navigationResult = await keyboardMouseNavigation(
  //       pageOrController,
  //       recentInteractions,
  //       gherkinStep,
  //       framework
  //     );

  //     return navigationResult || { success: false, healler: 'No Element Found to heal', strategy: 'interaction' };
  //   }
  //   } catch (error) {
  //     console.warn('Interaction healing failed:', error);
  //     return { success: false, healler: 'No Element Found to heal', strategy: 'interaction' };
  //   }
  // }


  /**
   * Strategy 3: Execution History-Based Healing
   * Leverages logs from successful test runs within the past 2 weeks
   */
  // async function historyBasedHealing(
  //   pageOrController: any,
  //   errorMsg: string,
  //   gherkinStep: string,
  //   framework: 'playwright' | 'testcafe'
  // ): Promise<HealingStrategyResult | null> {
  //   try {
  //     logger.info('📊 Analyzing execution history...');

  //     // Get historical execution data from the past 2 weeks
  //     const twoWeeksAgo = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000);
  //     const historicalData = await getHistoricalExecutionData(gherkinStep, twoWeeksAgo);

  //     if (historicalData.length === 0) {
  //       return { success: false, confidence: 0, strategy: 'history' };
  //     }

  //     // Analyze patterns and predict best selector
  //     const predictedSelector = await predictBestSelector(historicalData, errorMsg);

  //     if (predictedSelector) {
  //       const testResult = await testSelector(pageOrController, predictedSelector.selector, framework);

  //       if (testResult.success) {
  //         const healedStep = await convertLocatorToStep(
  //           predictedSelector.selector,
  //           predictedSelector.type,
  //           gherkinStep,
  //           framework
  //         );

  //         return {
  //           success: true,
  //           healedStep,
  //           confidence: predictedSelector.confidence,
  //           strategy: 'history-prediction',
  //           metadata: {
  //             historicalMatches: historicalData.length,
  //             prediction: predictedSelector
  //           }
  //         };
  //       }
  //     }

  //     return { success: false, confidence: 0, strategy: 'history' };
  //   } catch (error) {
  //     console.warn('History healing failed:', error);
  //     return { success: false, confidence: 0, strategy: 'history' };
  //   }
  // }

  /**
   * Strategy 4: Screenshot-Based Healing
   * Implements visual element recovery using screenshot analysis
   * Following the same robust pattern as CDP-based healing
   */
  async function screenshotBasedHealing(
    pageOrController: any,
    pageUrl: string,
    errorMsg: string,
    gherkinStep: string,
    framework: any
  ): Promise<any> {
    try {
      let domAnalysis: any;

      if (framework === 'playwright') {
        // Use existing Playwright CDP extraction
        domAnalysis = await extractComprehensiveDOMData(pageOrController, {
          enableCDPStrategy: true,
          enableAccessibilityTreeStrategy: true,
          generateWCAGCompliantSelectors: true,
          debugMode: false
        });
      } else {
        // TestCafe CDP extraction using native CDP session
        domAnalysis = await extractTestCafeCDPData(pageOrController);
      }
      
      const skiewdHealer = await healLocator(errorMsg, gherkinStep, domAnalysis);
      const imagebuffer: any = await takeFrameworkScreenshot(pageOrController, framework);
      const visionClient = new VisualHealingService();
      
      // Get response from visual healing service with retry logic (similar to CDP healing)
      let responseformated: any;
      let retryCount = 0;
      const MAX_RETRIES = 2;
      let screenshotPrompt: string = '';
      let screenshotResponse: string = '';
      
      while (retryCount <= MAX_RETRIES) {
        try {
          responseformated = await visionClient.healLocator(imagebuffer, skiewdHealer, pageUrl, errorMsg, gherkinStep, framework);
          
          // Capture the prompt and response for JSONL logging
          if (retryCount === 0) {
            screenshotPrompt = visionClient.generatePrompt(errorMsg, skiewdHealer, pageUrl, gherkinStep, framework);
            screenshotResponse = JSON.stringify(responseformated);
          }
          
          // Validate response format (same pattern as CDP healing)
          if (responseformated?.suggestions?.length > 0) {
            // Standard format with suggestions array - proceed to testing
            break;
          } else if (responseformated?.reasoning) {
            // Try to extract suggestions from reasoning field (embedded JSON)
            try {
              const reasoningText = responseformated.reasoning;
              const jsonMatch = reasoningText.match(/```json\s*([\s\S]*?)\s*```/);
              if (jsonMatch) {
                const extractedJson = JSON.parse(jsonMatch[1]);
                // Handle both array and single object formats
                if (Array.isArray(extractedJson)) {
                  responseformated.suggestions = extractedJson.map(item => ({
                    recommended_locator: item.selector,
                    confidence: item.confidence || 0.8,
                    strategy: item.strategy || 'unknown',
                    reasoning: item.reasoning || '',
                    fix_type_description: item.fix_type_description || ''
                  }));
                } else if (extractedJson.selector) {
                  responseformated.suggestions = [{
                    recommended_locator: extractedJson.selector,
                    confidence: extractedJson.confidence || 0.8,
                    strategy: extractedJson.strategy || 'unknown',
                    reasoning: extractedJson.reasoning || '',
                    fix_type_description: extractedJson.fix_type_description || ''
                  }];
                }
                
                // If we successfully extracted suggestions, break out of retry loop
                if (responseformated.suggestions?.length > 0) {
                  break;
                }
              }
            } catch (parseError) {
              logger.warn(`JSON parsing failed for screenshot healing (attempt ${retryCount + 1}/${MAX_RETRIES + 1}):`, parseError);
            }
          }
          
          // If we get here, the response wasn't valid, so retry
          retryCount++;
          if (retryCount <= MAX_RETRIES) {
            logger.warn(`Screenshot healing attempt ${retryCount}/${MAX_RETRIES + 1} failed, retrying...`);
          }
        } catch (error) {
          logger.warn(`Screenshot healing attempt ${retryCount + 1}/${MAX_RETRIES + 1} failed:`, error);
          retryCount++;
          if (retryCount > MAX_RETRIES) {
            throw error;
          }
        }
      }
      
      // Final validation - same pattern as CDP healing
      if (!responseformated?.suggestions?.length) {
        logger.warn('Screenshot healing failed: No valid suggestions after all retry attempts');
        return { 
          success: false, 
          confidence: 0, 
          strategy: 'screenshot', 
          error: 'No valid suggestions after retries',
          healler: 'No suggestions could be extracted from visual healing service'
        };
      }
      
      // Test the healed selector (same pattern as CDP healing)
      const healed = await testHealedSelector(pageOrController, responseformated.suggestions, framework);
      if (healed.success) {
        // Log successful screenshot healing data to JSONL (only if TRAINING_DATA=true)
        const healedLocator = healed.locator || 'Unknown locator';
        jsonlLogger.logHealingData(screenshotPrompt, screenshotResponse, healedLocator);
        
        return { success: true, healler: healed, strategy: 'screenshot' };
      } else {
        logger.warn(`Healed selector not found in screenshot healing: ${JSON.stringify(healed.locator, null, 2)}`);
        return { 
          success: false, 
          confidence: 0, 
          strategy: 'screenshot', 
          error: 'Healed selector not found',
          healler: healed
        };
      }
    } catch (error) {
      logger.warn('Screenshot healing failed:', error);
      return { 
        success: false, 
        confidence: 0, 
        strategy: 'screenshot',
        error: String(error),
        healler: 'Screenshot healing failed with error'
      };
    }
  }




  /**
   * Extract TestCafe CDP data using native CDP session
   * Enhanced to match Playwright's comprehensive DOM analysis capabilities
   */
export async function extractTestCafeCDPData(testController:any, options: ExtractUIElementsOptions = {}
): Promise<ComprehensiveDOMAnalysis> {
  const startTime = Date.now();
  const defaultOptions: ExtractUIElementsOptions = {
    enableCDPStrategy: true,
    enableAccessibilityTreeStrategy: true,
    generateWCAGCompliantSelectors: true,
    includeHidden: false,
    includeIframes: true,
    includeShadowDOM: true,
    debugMode: false,
    maxDepth: -1 // Maximum depth for complete DOM traversal
  };
    try {
// Set a native dialog handler to automatically dismiss any dialogs
    await testController.setNativeDialogHandler(() => true);

  
      const mergedOptions = { ...defaultOptions, ...options };

      if (mergedOptions.debugMode) {
        
      }
      // Step 1: Extract page metadata
        const pageUrl = await testController.eval(() => document.location.href);
        const timestamp = new Date().toISOString();
        const viewport = await ClientFunction(() => ({
            width: window.innerWidth,
            height: window.innerHeight,
        }))();
        const deviceScaleFactor = await ClientFunction(() => window.devicePixelRatio || 1)();

        if (mergedOptions.debugMode) {
          
        }
      // Step 2: Extract CDP DOM nodes (Primary Strategy)
          if (mergedOptions.debugMode) {
    
          }
          const cdpNodes = await extractCDPDOMNodes(testController);
  
          // Step 3: Extract accessibility tree nodes (Fallback Strategy)
          if (mergedOptions.debugMode) {
    
          }
          const accessibilityNodes = await extractAccessibilityTreeNodes(testController);

          if (mergedOptions.debugMode) {
            
          }
    // Step 4: Process elements and generate comprehensive data
    const elements: ComprehensiveElementData[] = [];
    const statistics = {
      totalElements: 0,
      interactiveElements: 0,
      elementsWithIds: 0,
      elementsWithTestIds: 0,
      elementsWithAriaLabels: 0,
      frameworkComponents: {
        react: 0,
        angular: 0,
        vue: 0,
        materialUI: 0,
        agGrid: 0
      },
      averageConfidenceScore: 0,
      wcagCompliantElements: 0
    };

    let totalConfidenceScore = 0;
    let confidenceCount = 0;

    // Interactive element types for filtering
    const interactiveTypes = [
      'input', 'button', 'select', 'textarea', 'a', 'form', 'span', 'div', 'label', 'fieldset', 'legend',
      'iframe', 'canvas', 'svg', 'video', 'audio', 'picture', 'source', 'track', 'details', 'summary',
      'dialog', 'progress', 'meter', 'output', 'datalist', 'option', 'optgroup', 'map', 'area', 'object',
      'embed', 'param', 'time', 'mark', 'abbr', 'cite', 'q', 'blockquote', 'code', 'pre', 'kbd', 'samp',
      'sub', 'sup', 'ruby', 'rt', 'rp', 'bdi', 'bdo', 'wbr', 'template', 'script', 'noscript', 'style',
      'link', 'meta', 'base', 'body', 'header', 'footer', 'nav', 'section', 'article', 'aside', 'h1',
      'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'caption', 'thead',
      'tbody', 'tfoot', 'tr', 'td', 'th', 'col', 'colgroup', 'figure', 'figcaption', 'main', 'small',
      'big', 'hr', 'br', 'em', 'strong', 'i', 'b', 'u', 's', 'del', 'ins', 'cite', 'dfn', 'var', 'address'
    ];
    const interactiveRoles = [
      'button', 'link', 'textbox', 'combobox', 'listbox', 'checkbox', 'radio', 'tab', 'menuitem',
      'slider', 'spinbutton', 'progressbar', 'alert', 'dialog', 'tooltip', 'status', 'log', 'marquee',
      'timer', 'separator', 'heading', 'navigation', 'region', 'search', 'grid', 'row', 'cell', 'columnheader',
      'rowheader', 'tree', 'treeitem', 'list', 'listitem', 'group', 'application', 'banner', 'complementary',
      'contentinfo', 'form', 'main', 'presentation', 'alertdialog', 'feed', 'figure', 'article', 'note',
      'definition', 'directory', 'document', 'img', 'math', 'toolbar', 'tooltip', 'menu', 'menubar', 'menuitemcheckbox',
      'menuitemradio', 'none', 'progressbar', 'scrollbar', 'switch', 'tablist', 'tabpanel', 'term', 'text',
      'togglebutton', 'treegrid', 'widget', 'window'
    ];

    for (const [, cdpNode] of Object.entries(cdpNodes)) {
      if (!cdpNode.nodeName) {
        continue;
      }
      const nodeName = cdpNode.nodeName.toLowerCase();
      const attributes: Record<string, string> = {};

// Parse CDP attributes
      if (cdpNode.attributes && Array.isArray(cdpNode.attributes)) {
        for (let i = 0; i < cdpNode.attributes.length; i += 2) {
          const attrName = cdpNode.attributes[i];
          const attrValue = cdpNode.attributes[i + 1];
          if (attrName && attrValue !== undefined) {
            attributes[attrName] = attrValue;
          }
        }
      }

      // Check if element is interactive or has important attributes
      const isInteractiveType = interactiveTypes.includes(nodeName);
      const hasInteractiveRole = attributes.role && interactiveRoles.includes(attributes.role);
      const hasImportantAttributes = attributes.id || attributes['data-testid'] || attributes['aria-label'] || attributes.role;
      const hasClickHandler = attributes.onclick || attributes.tabindex !== undefined;

      if (isInteractiveType || hasInteractiveRole || hasImportantAttributes || hasClickHandler) {
        // Extract text content from the element and its children
        const textContent = extractTextContent(cdpNode, cdpNodes);

        // Generate locator candidates with confidence scoring
        const locatorCandidates = generateLocatorCandidates(attributes, nodeName, textContent);

        // Detect framework hints
        const frameworkHints = detectFrameworkHints(attributes, nodeName);

        // Generate accessibility data
        const accessibility = generateAccessibilityData(attributes, textContent, cdpNode, cdpNodes, nodeName);

        // Generate visual properties (basic implementation)
        const visual = {
          isVisible: !attributes.hidden && attributes.style !== 'display: none',
          styles: attributes.style ? parseStyleString(attributes.style) : {}
        };

        // Generate parent hierarchy
        const parentHierarchy = generateElementPath(cdpNode, cdpNodes);

        // Detect event handlers
        const eventHandlers = detectEventHandlers(attributes);

        // Determine interaction type
        const interactionType = determineInteractionType(nodeName, attributes);

        const elementData: ComprehensiveElementData = {
          tagName: nodeName,
          nodeId: cdpNode.nodeId,
          nodeType: cdpNode.nodeType,
          attributes,
          textContent: textContent || undefined,
          accessibility,
          visual,
          frameworkHints,
          locatorCandidates,
          parentHierarchy,
          eventHandlers,
          isInteractable: !attributes.disabled && visual.isVisible,
          interactionType
        };

        elements.push(elementData);

        // Update statistics
        statistics.totalElements++;
        if (elementData.isInteractable) statistics.interactiveElements++;
        if (attributes.id) statistics.elementsWithIds++;
        if (attributes['data-testid']) statistics.elementsWithTestIds++;
        if (attributes['aria-label']) statistics.elementsWithAriaLabels++;

        // Framework component counting
        if (frameworkHints.react) statistics.frameworkComponents.react++;
        if (frameworkHints.angular) statistics.frameworkComponents.angular++;
        if (frameworkHints.vue) statistics.frameworkComponents.vue++;
        if (frameworkHints.materialUI) statistics.frameworkComponents.materialUI++;
        if (frameworkHints.agGrid) statistics.frameworkComponents.agGrid++;

        // WCAG compliance counting
        const wcagCompliantSelectors = locatorCandidates.filter(loc => loc.isWCAGCompliant);
        if (wcagCompliantSelectors.length > 0) statistics.wcagCompliantElements++;

        // Confidence score calculation
        if (locatorCandidates.length > 0) {
          const avgConfidence = locatorCandidates.reduce((sum, loc) => sum + loc.confidence, 0) / locatorCandidates.length;
          totalConfidenceScore += avgConfidence;
          confidenceCount++;
        }
      }
    }

    // Calculate average confidence score
    statistics.averageConfidenceScore = confidenceCount > 0 ?
      Math.round((totalConfidenceScore / confidenceCount) * 100) / 100 : 0;

    const extractionTime = Date.now() - startTime;

    const result: ComprehensiveDOMAnalysis = {
      pageUrl,
      timestamp,
      viewport: {
        width: viewport.width,
        height: viewport.height,
        deviceScaleFactor
      },
      elements,
      statistics,
      extractionMetadata: {
        cdpNodesExtracted: Object.keys(cdpNodes).length,
        accessibilityNodesExtracted: Object.keys(accessibilityNodes).length,
        extractionTime,
        options: mergedOptions,
        strategies: ['CDP Session', 'Accessibility Tree', 'WCAG Compliance']
      }
    };

    if (mergedOptions.debugMode) {
      
      
    }

    function simplifyElement(element: any) {
      return {
        tagName: element.tagName || undefined,
        id: element.attributes?.id || undefined,
        class: element.attributes?.class || undefined,
        text: element.textContent || undefined,
        role: element.accessibility?.role || undefined,
        name: element.accessibility?.name || undefined,
        isVisible: element.visual?.isVisible ?? undefined,
        boundingBlock: element.visual?.boundingBox ?? undefined,
        isInteractable: element.isInteractable ?? undefined,
        viewPoint: element.viewPoint || undefined,
        locators: Array.isArray(element.locatorCandidates)
          ? element.locatorCandidates
            .filter((c: any) => c && c.type && c.selector)
            .map((c: any) => ({
              type: c.type,
              selector: c.selector,
              confidence: c.confidence
            }))
          : [],
        parentHierarchy: Array.isArray(element.parentHierarchy) ? element.parentHierarchy.join(' > ') : undefined
      };
    }
    
    const simplifiedElements: any =  result.elements.map(simplifyElement);
    const cleanedDomAnalysis = simplifiedElements.map((obj: Record<string, any>) => {
    const cleanedObj: { [key: string]: any } = {};
        Object.keys(obj).forEach(key => {
          const value = obj[key];
          if (value !== undefined) {
            cleanedObj[key] = value;
          }
        });
      return cleanedObj;
    });
    return {
      pageUrl,
      timestamp,
      viewport: {
        width: viewport.width,
        height: viewport.height,
        deviceScaleFactor
      },
      elements: cleanedDomAnalysis,
      statistics,
      extractionMetadata: {
        cdpNodesExtracted: Object.keys(cdpNodes).length,
        accessibilityNodesExtracted: Object.keys(accessibilityNodes).length,
        extractionTime,
        options: mergedOptions,
        strategies: ['CDP Session', 'Accessibility Tree', 'WCAG Compliance']
      }
    };

  } catch (error) {
    logger.error('❌ Error in TestCafe CDP data extraction:', error);
    throw new Error(`Failed to extract TestCafe CDP data: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

  /**
   * Fallback TestCafe DOM extraction using ClientFunction
   */
  export async function extractTestCafeSimplifiedDOM(testController: any): Promise<ComprehensiveDOMAnalysis> {
    const extractDOMData = ClientFunction(() => {
      const elements: any[] = [];
      const allElements = document.querySelectorAll('*');

      allElements.forEach((el, index) => {
        if (index > 1000) return; // Limit for performance

        const rect = el.getBoundingClientRect();
        const styles = window.getComputedStyle(el);

        // Get attributes
        const attributes: Record<string, string> = {};
        for (const attr of el.attributes) {
          attributes[attr.name] = attr.value;
        }

        elements.push({
          tagName: el.tagName.toLowerCase(),
          nodeId: index,
          nodeType: el.nodeType,
          attributes,
          textContent: el.textContent?.trim() || undefined,
          accessibility: {
            role: el.getAttribute('role') || undefined,
            name: el.getAttribute('aria-label') || el.getAttribute('title') || undefined,
            ariaLabel: el.getAttribute('aria-label') || undefined,
          },
          visual: {
            boundingBox: {
              x: rect.x,
              y: rect.y,
              width: rect.width,
              height: rect.height
            },
            styles: {
              display: styles.display,
              visibility: styles.visibility,
              opacity: styles.opacity
            },
            isVisible: rect.width > 0 && rect.height > 0 && styles.display !== 'none',
            isInViewport: rect.x >= 0 && rect.y >= 0
          },
          frameworkHints: {},
          locatorCandidates: [],
          parentHierarchy: [],
          eventHandlers: [],
          isInteractable: ['button', 'input', 'select', 'textarea', 'a'].includes(el.tagName.toLowerCase())
        });
      });

      return {
        pageUrl: window.location.href,
        timestamp: new Date().toISOString(),
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight,
          deviceScaleFactor: window.devicePixelRatio || 1
        },
        elements
      };
    });

    const data = await extractDOMData();

    return {
      ...data,
      statistics: calculateTestCafeDOMStatistics(data.elements),
      extractionMetadata: {
        cdpNodesExtracted: data.elements.length,
        accessibilityNodesExtracted: 0,
        extractionTime: 0,
        strategies: ['TestCafe ClientFunction Fallback']
      }
    };
  }

  /**
   * Get TestCafe page information
   */
  async function getTestCafePageInfo(testController: any): Promise<{ url: string; viewport: any }> {
    const getPageInfo = ClientFunction(() => ({
      url: window.location.href,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
        deviceScaleFactor: window.devicePixelRatio || 1
      }
    }));

    return await getPageInfo();
  }

  /**
   * Process TestCafe CDP nodes into comprehensive element data
   */
  async function processTestCafeCDPNodes(
    nodes: any[],
    accessibilityNodes: any[],
    cdpSession: any,
    testController: any
  ): Promise<ComprehensiveElementData[]> {
    const elements: ComprehensiveElementData[] = [];

    for (const node of nodes.slice(0, 500)) { // Limit for performance
      if (node.nodeType === 1) { // Element nodes only
        try {
          const element = await processTestCafeCDPNode(node, accessibilityNodes, cdpSession);
          if (element) {
            elements.push(element);
          }
        } catch (error) {
          logger.warn('Failed to process CDP node:', error);
        }
      }
    }

    return elements;
  }

  /**
   * Process individual TestCafe CDP node
   */
  async function processTestCafeCDPNode(
    node: any,
    accessibilityNodes: any[],
    cdpSession: any
  ): Promise<ComprehensiveElementData | null> {
    try {
      // Get box model for positioning
      let boxModel = null;
      try {
        const boxResult = await cdpSession.DOM.getBoxModel({ nodeId: node.nodeId });
        boxModel = boxResult.model;
      } catch (error) {
        // Box model not available for this node
      }

      // Find accessibility info
      const accessibilityInfo = accessibilityNodes.find(axNode =>
        axNode.backendDOMNodeId === node.backendNodeId
      );

      // Get computed styles
      let computedStyles: any = {};
      try {
        const stylesResult = await cdpSession.CSS.getComputedStyleForNode({ nodeId: node.nodeId });
        computedStyles = stylesResult.computedStyle.reduce((acc: any, style: any) => {
          acc[style.name] = style.value;
          return acc;
        }, {});
      } catch (error) {
        // Styles not available
      }

      return {
        tagName: node.nodeName.toLowerCase(),
        nodeId: node.nodeId,
        nodeType: node.nodeType,
        attributes: node.attributes ? arrayToAttributeMap(node.attributes) : {},
        textContent: node.nodeValue || undefined,
        accessibility: {
          role: accessibilityInfo?.role?.value || getAttributeValue(node.attributes, 'role') || undefined,
          name: accessibilityInfo?.name?.value || undefined,
          ariaLabel: getAttributeValue(node.attributes, 'aria-label') || undefined,
        },
        visual: {
          boundingBox: boxModel ? {
            x: boxModel.content[0],
            y: boxModel.content[1],
            width: boxModel.content[4] - boxModel.content[0],
            height: boxModel.content[5] - boxModel.content[1]
          } : { x: 0, y: 0, width: 0, height: 0 },
          styles: computedStyles,
          isVisible: computedStyles.display !== 'none' && computedStyles.visibility !== 'hidden',
          isInViewport: true // Simplified for now
        },
        frameworkHints: {},
        locatorCandidates: [],
        parentHierarchy: [],
        eventHandlers: [],
        isInteractable: ['button', 'input', 'select', 'textarea', 'a'].includes(node.nodeName.toLowerCase())
      };
    } catch (error) {
      logger.warn('Failed to process individual CDP node:', error);
      return null;
    }
  }

  /**
   * Get attribute value from CDP attributes array
   */
  function getAttributeValue(attributes: string[] | undefined, attributeName: string): string | undefined {
    if (!attributes) return undefined;

    for (let i = 0; i < attributes.length; i += 2) {
      if (attributes[i] === attributeName) {
        return attributes[i + 1];
      }
    }
    return undefined;
  }

  /**
   * Convert CDP attributes array to map
   */
  function arrayToAttributeMap(attributes: string[]): Record<string, string> {
    const map: Record<string, string> = {};
    for (let i = 0; i < attributes.length; i += 2) {
      if (attributes[i] && attributes[i + 1] !== undefined) {
        map[attributes[i]] = attributes[i + 1];
      }
    }
    return map;
  }

  /**
   * Calculate DOM statistics for TestCafe
   */
  function calculateTestCafeDOMStatistics(elements: any[]): any {
    return {
      totalElements: elements.length,
      interactableElements: elements.filter(el => el.isInteractable).length,
      visibleElements: elements.filter(el => el.visual?.isVisible).length,
      elementsWithText: elements.filter(el => el.textContent).length,
      elementsWithIds: elements.filter(el => el.attributes?.id).length,
      elementsWithClasses: elements.filter(el => el.attributes?.class).length,
      elementsWithAriaLabels: elements.filter(el => el.accessibility?.ariaLabel).length
    };
  }

  /**
   * Test a selector against the page/controller
   */
  export async function testSelector(
    pageOrController: any,
    selector: string,
    framework: 'playwright' | 'testcafe'
  ): Promise<TestResult> {
    try {
      if (framework === 'playwright') {
        const elements = await pageOrController.locator(selector).all();
        return { success: elements.length > 0, count: elements.length };
      } else {
        // TestCafe
        const testSelectorFunc = ClientFunction((sel: string) => {
          const elements = document.querySelectorAll(sel);
          return elements.length;
        });
        const count = await testSelectorFunc(selector);
        return { success: count > 0, count };
      }
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Convert locator to framework-specific step
   */
  export async function convertLocatorToStep(
    selector: string,
    selectorType: string,
    originalGherkinStep: string,
    framework: 'playwright' | 'testcafe'
  ): Promise<string> {
    // Extract action from original step
    const action = extractActionFromGherkinStep(originalGherkinStep);

    if (framework === 'playwright') {
      switch (action) {
        case 'click':
          return `await page.locator('${selector}').click()`;
        case 'fill':
        case 'type':
          return `await page.locator('${selector}').fill('text')`;
        case 'check':
          return `await page.locator('${selector}').check()`;
        case 'uncheck':
          return `await page.locator('${selector}').uncheck()`;
        default:
          return `await page.locator('${selector}').click()`;
      }
    } else {
      // TestCafe
      switch (action) {
        case 'click':
          return `await t.click(Selector('${selector}'))`;
        case 'fill':
        case 'type':
          return `await t.typeText(Selector('${selector}'), 'text')`;
        case 'check':
          return `await t.click(Selector('${selector}'))`;
        case 'uncheck':
          return `await t.click(Selector('${selector}'))`;
        default:
          return `await t.click(Selector('${selector}'))`;
      }
    }
  }

  /**
   * Extract action from Gherkin step
   */
  function extractActionFromGherkinStep(gherkinStep: string): string {
    const step = gherkinStep.toLowerCase();
    if (step.includes('click')) return 'click';
    if (step.includes('fill') || step.includes('type') || step.includes('enter')) return 'fill';
    if (step.includes('check') && !step.includes('uncheck')) return 'check';
    if (step.includes('uncheck')) return 'uncheck';
    if (step.includes('select')) return 'select';
    return 'click'; // default
  }

  /**
   * Test framework-specific locator
   */
  export async function testFrameworkLocator(
    pageOrController: any,
    locator: any,
    framework: 'playwright' | 'testcafe'
  ): Promise<TestResult> {
    try {
      if (framework === 'playwright') {
        // Construct Playwright locator based on method and args
        let playwrightLocator;
        switch (locator.method) {
          case 'getByRole':
            playwrightLocator = pageOrController.getByRole(locator.args[0], locator.args[1]);
            break;
          case 'getByText':
            playwrightLocator = pageOrController.getByText(locator.args[0]);
            break;
          case 'getByLabel':
            playwrightLocator = pageOrController.getByLabel(locator.args[0]);
            break;
          case 'locator':
            playwrightLocator = pageOrController.locator(locator.args[0]);
            break;
          default:
            playwrightLocator = pageOrController.locator(locator.args[0]);
        }

        const elements = await playwrightLocator.all();
        return { success: elements.length > 0, count: elements.length };
      } else {
        // TestCafe - convert to selector string and test
        const selectorString = convertLocatorToSelectorString(locator);
        return await testSelector(pageOrController, selectorString, framework);
      }
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Convert locator object to selector string
   */
  function convertLocatorToSelectorString(locator: any): string {
    switch (locator.method) {
      case 'getByRole':
        return `[role="${locator.args[0]}"]`;
      case 'getByText':
        return `*:contains("${locator.args[0]}")`;
      case 'getByLabel':
        return `[aria-label="${locator.args[0]}"], label:contains("${locator.args[0]}") input`;
      case 'locator':
      default:
        return locator.args[0];
    }
  }

  /**
   * Get recent successful interactions (Strategy 2 helper)
   */
  export async function getRecentSuccessfulInteractions(gherkinStep: string): Promise<InteractionHistoryData[]> {
    // This would typically query BigQuery storage
    // For now, return empty array as placeholder

    return [];
  }

  /**
   * Semantic interaction replay (Strategy 2 helper)
   */
  // export async function semanticInteractionReplay(
  //   pageOrController: any,
  //   interactions: InteractionHistoryData[],
  //   gherkinStep: string,
  //   framework: 'playwright' | 'testcafe'
  // ): Promise<HealingStrategyResult | null> {
  //   logger.info(`🧠 Performing semantic interaction replay for: ${gherkinStep}`);

  //   // Analyze interaction patterns and find semantic matches
  //   for (const interaction of interactions) {
  //     if (interaction.success && interaction.selector) {
  //       const testResult = await testSelector(pageOrController, interaction.selector, framework);
  //       if (testResult.success) {
  //         const healedStep = await convertLocatorToStep(
  //           interaction.selector,
  //           interaction.selectorType,
  //           gherkinStep,
  //           framework
  //         );

  //         return {
  //           success: true,
  //           healedStep,
  //           confidence: 0.75,
  //           strategy: 'interaction-semantic',
  //           metadata: { semanticMatch: interaction }
  //         };
  //       }
  //     }
  //   }

  //   return null;
  // }

  /**
   * Keyboard/mouse navigation (Strategy 2 helper)
   */
  // export async function keyboardMouseNavigation(
  //   pageOrController: any,
  //   interactions: InteractionHistoryData[],
  //   gherkinStep: string,
  //   framework: 'playwright' | 'testcafe'
  // ): Promise<HealingStrategyResult | null> {
  //   logger.info(`⌨️ Performing keyboard/mouse navigation for: ${gherkinStep}`);

  //   // Analyze navigation patterns
  //   const navigationPatterns = interactions.filter(i =>
  //     i.metadata?.navigationType === 'keyboard' || i.metadata?.navigationType === 'mouse'
  //   );

  //   for (const pattern of navigationPatterns) {
  //     if (pattern.selector) {
  //       const testResult = await testSelector(pageOrController, pattern.selector, framework);
  //       if (testResult.success) {
  //         const healedStep = await convertLocatorToStep(
  //           pattern.selector,
  //           pattern.selectorType,
  //           gherkinStep,
  //           framework
  //         );

  //         return {
  //           success: true,
  //           healedStep,
  //           confidence: 0.70,
  //           strategy: 'interaction-navigation',
  //           metadata: { navigationPattern: pattern }
  //         };
  //       }
  //     }
  //   }

  //   return null;
  // }

  /**
   * Get historical execution data (Strategy 3 helper)
   */
  export async function getHistoricalExecutionData(
    gherkinStep: string,
    since: Date
  ): Promise<HistoricalExecutionData[]> {

    // This would typically query BigQuery storage
    // For now, return empty array as placeholder
    return [];
  }

  /**
   * Predict best selector (Strategy 3 helper)
   */
  export async function predictBestSelector(
    historicalData: HistoricalExecutionData[],
    errorMsg: string
  ): Promise<PredictedSelector | null> {


    if (historicalData.length === 0) {
      return null;
    }

    // Analyze patterns and predict best selector
    const successfulSelectors = historicalData
      .filter(data => data.success)
      .map(data => ({ selector: data.selector, type: data.selectorType, confidence: data.confidence }));

    if (successfulSelectors.length > 0) {
      // Return the most confident selector
      const bestSelector = successfulSelectors.reduce((best, current) =>
        current.confidence > best.confidence ? current : best
      );

      return {
        selector: bestSelector.selector,
        type: bestSelector.type,
        confidence: bestSelector.confidence,
        reasoning: `Based on ${successfulSelectors.length} successful historical executions`
      };
    }

    return null;
  }

  /**
   * Take framework screenshot (Strategy 4 helper)
   */
  export async function takeFrameworkScreenshot(
    pageOrController: any,
    framework: 'playwright' | 'testcafe'
  ): Promise<string | null> {
    try {
  

      if (framework === 'playwright') {
        const screenshot = await pageOrController.screenshot({ type: 'png' });
        return screenshot;
      } else {
        // TestCafe - takeScreenshot returns a file path, we need to read it and convert to buffer
        const fs = require('fs');
        const path = require('path');
        
        try {
          // Take screenshot and get the file path
          const screenshotPath = await pageOrController.takeScreenshot();
          
          // Read the file and convert to buffer
          if (screenshotPath && fs.existsSync(screenshotPath)) {
            const screenshotBuffer = fs.readFileSync(screenshotPath);
            return screenshotBuffer;
          } else {
            logger.warn('TestCafe screenshot file not found at path:', screenshotPath);
            return null;
          }
        } catch (error) {
          logger.warn('Failed to read TestCafe screenshot file:', error);
          return null;
        }
      }
    } catch (error) {
      logger.warn('Failed to take screenshot:', error);
      return null;
    }
  }

  /**
   * Get reference screenshots (Strategy 4 helper)
   */
  export async function getReferenceScreenshots(gherkinStep: string): Promise<string[]> {

    // This would typically query BigQuery storage for stored screenshots
    // For now, return empty array as placeholder
    return [];
  }

  /**
   * Analyze visual differences (Strategy 4 helper)
   */
  export async function analyzeVisualDifferences(
    currentScreenshot: string | null,
    referenceScreenshots: string[],
    errorMsg: string
  ): Promise<VisualAnalysisResult> {


    // Placeholder implementation
    // In a real implementation, this would use image comparison algorithms
    return {
      confidence: 0.5,
      differences: [],
      targetElement: undefined
    };
  }
  interface Candidate {
    selector: string;
    validate: () => Promise<boolean>;
  }
  /**
   * Generate selector from visual element (Strategy 4 helper)
   */
  export async function generateSelectorFromVisualElement(
    pageOrController: any,
    targetElement: any,
    framework: 'playwright' | 'testcafe'
  ): Promise<VisualSelector | null> {


    try {
      if (framework === 'playwright') {
        // Use Playwright's elementHandle.locator to find element at coordinates
        const element = await pageOrController.locator(`*`).first();
        // This is a simplified implementation
        return {
          selector: `*:nth-child(1)`, // Placeholder
          type: 'css',
          confidence: 0.6,
          coordinates: targetElement
        };
      } else {
        // TestCafe implementation
        return {
          selector: `*:nth-child(1)`, // Placeholder
          type: 'css',
          confidence: 0.6,
          coordinates: targetElement
        };
      }
    } catch (error) {
      logger.warn('Failed to generate selector from visual element:', error);
      return null;
    }
  }
  export function filterDomElementsByKeywords(
    domElements: any[],
    keywordsString: string
  ): any[] {
    // if (!Array.isArray(domElements)) {
    //    return [];
    //  }
     // Filter out any undefined or null elements from the array first
    const validDomElements = domElements.filter(el => el);

    const keywords = JSON.parse(keywordsString.replace(/'/g, '"'))
      .map((k: string) => k.toLowerCase().trim());

    return validDomElements.filter(el => {
      const content = [
        el.tagName,
        el.id,
        el.class,
        el.text || el.textContent || el.name,
        el.role,
        el.name,
        el.placeholder,
        el.alt,
        el.title,
        el.testId,
        el.parentHierarchy,
        ...(el.locators?.map((l: LocatorStrategy) => l.selector) || [])
      ]
        .map(p => p)
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

      return keywords.some((keyword: string) => content.includes(keyword));
    });
  }

  export async function healLocator(
    errorMessage: string,
    gherkinStep: string,
    domElements: any
  ): Promise<any> {
    const Prompts = `Extract semantic keywords from the following BDD step and error message that best describe the target UI element.

Output:
Return a list of concise, relevant tokens or phrases (e.g., "submit", "email", "login") that would help identify the UI element.

The output must be a valid JSON array of strings, with each token enclosed in double quotes. For example:
["find", "agent", "button"]

BDD Step: ${gherkinStep}
Error Message: ${errorMessage}

Instructions:
- The output should be a valid JSON array of strings and **MUST NOT** have any code decorator, newline character, or any other code decorator.
- The output should be a valid JSON array of strings, with each token enclosed in double quotes.
- Do not include any text before or after the JSON array.
- Return ONLY the JSON array, nothing else.
`;

    let semanticToken = (await adkClient.callGeminiModel(Prompts));
    
    // Clean up the response to extract valid JSON
    if (semanticToken.startsWith('```json') && semanticToken.endsWith('```')) {
      semanticToken = semanticToken.slice(7, -3).trim();
    } else if (semanticToken.startsWith('```') && semanticToken.endsWith('```')) {
      semanticToken = semanticToken.slice(3, -3).trim();
    } else if (semanticToken.startsWith('json')) {
      // Remove "json" prefix if present
      semanticToken = semanticToken.replace(/^json\s*/, '').trim();
    }
    
    // Try to parse the JSON and handle errors gracefully
    let keywords: string[] = [];
    try {
      // First try direct parsing
      keywords = JSON.parse(semanticToken);
    } catch (parseError) {
      try {
        // Try to clean up common formatting issues
        let cleanedToken = semanticToken
          .replace(/'/g, '"')  // Replace single quotes with double quotes
          .replace(/\n/g, '')  // Remove newlines
          .replace(/\r/g, '')  // Remove carriage returns
          .trim();
        
        // If it still doesn't start with [, try to find the array
        if (!cleanedToken.startsWith('[')) {
          const arrayMatch = cleanedToken.match(/\[.*\]/);
          if (arrayMatch) {
            cleanedToken = arrayMatch[0];
          }
        }
        
        keywords = JSON.parse(cleanedToken);
      } catch (secondError) {
        logger.warn('Failed to parse semantic tokens from LLM response:', secondError);
        logger.warn('Raw response:', semanticToken);
        
        // Fallback to extracting keywords manually
        const fallbackKeywords = semanticToken
          .toLowerCase()
          .match(/["']([^"']+)["']/g)
          ?.map(k => k.replace(/["']/g, ''))
          .filter(k => k.length > 0) || [];
        
        if (fallbackKeywords.length > 0) {
      
          keywords = fallbackKeywords;
        } else {
          // Last resort: extract meaningful words from the response
          const words = semanticToken
            .toLowerCase()
            .match(/\b\w+\b/g)
            ?.filter(word => word.length > 2 && !['the', 'and', 'for', 'with', 'from', 'that', 'this', 'have', 'will', 'should', 'could', 'would'].includes(word)) || [];
          
          keywords = words.slice(0, 5); // Take first 5 meaningful words
      
        }
      }
    }
    
    // Ensure we have an array of strings
    if (!Array.isArray(keywords)) {
      keywords = [String(keywords)];
    }
    
    // Filter out empty or invalid keywords
    keywords = keywords.filter(k => typeof k === 'string' && k.trim().length > 0);
    

    
    // Handle both array and object formats
    let elementsArray: any[];
    if (Array.isArray(domElements)) {
      elementsArray = domElements;
    } else if (domElements && typeof domElements === 'object' && domElements.elements) {
      elementsArray = domElements.elements;
    } else {
      logger.warn('Invalid domElements format, expected array or object with elements property');
      return [];
    }
    
    return filterDomElementsByKeywords(elementsArray, JSON.stringify(keywords));
  }

  /**
   * Interface for accessibility element report
   */
  interface AccessibilityElementReport {
    tagName: string;
    nodeId: number;
    role?: string;
    name?: string;
    isAccessible: boolean;
    issues: string[];
    ariaAttributes: Record<string, string>;
    focusable: boolean;
    screenReaderText: string;
    wcagCompliant: boolean;
  }

  /**
   * Interface for accessibility report
   */
  interface AccessibilityReport {
    summary: {
      totalElements: number;
      accessibleElements: number;
      elementsWithIssues: number;
      wcagComplianceScore: number;
      ariaUsage: {
        total: number;
        roles: number;
        states: number;
        properties: number;
        liveRegions: number;
        landmarks: number;
      };
    };
    elements: AccessibilityElementReport[];
    issues: string[];
    recommendations: string[];
    wcagCompliance: {
      level: string;
      score: number;
      criteria: string[];
    };
  }

  /**
   * Generate comprehensive accessibility report based on WAI-ARIA 1.2 specification
   * @param {ComprehensiveDOMAnalysis} domAnalysis - DOM analysis result
   * @returns {AccessibilityReport} - Comprehensive accessibility report
   */
  export function generateAccessibilityReport(domAnalysis: ComprehensiveDOMAnalysis): AccessibilityReport {
    const report: AccessibilityReport = {
      summary: {
        totalElements: domAnalysis.elements.length,
        accessibleElements: 0,
        elementsWithIssues: 0,
        wcagComplianceScore: 0,
        ariaUsage: {
          total: 0,
          roles: 0,
          states: 0,
          properties: 0,
          liveRegions: 0,
          landmarks: 0
        }
      },
      elements: [],
      issues: [],
      recommendations: [],
      wcagCompliance: {
        level: 'A',
        score: 0,
        criteria: []
      }
    };

    // Analyze each element
    for (const element of domAnalysis.elements) {
      const elementReport: AccessibilityElementReport = {
        tagName: element.tagName,
        nodeId: element.nodeId,
        role: element.accessibility.role,
        name: element.accessibility.name,
        isAccessible: element.accessibility.isAccessible || false,
        issues: element.accessibility.accessibilityIssues || [],
        ariaAttributes: element.accessibility.ariaAttributes || {},
        focusable: element.accessibility.focusable || false,
        screenReaderText: element.accessibility.screenReaderText || '',
        wcagCompliant: element.locatorCandidates.some(loc => loc.isWCAGCompliant)
      };

      report.elements.push(elementReport);

      // Update summary statistics
      if (elementReport.isAccessible) {
        report.summary.accessibleElements++;
      }
      if (elementReport.issues.length > 0) {
        report.summary.elementsWithIssues++;
      }
      if (elementReport.wcagCompliant) {
        report.wcagCompliance.score++;
      }

      // Count ARIA usage
      if (element.accessibility.ariaAttributes) {
        report.summary.ariaUsage.total++;
        if (element.accessibility.role) report.summary.ariaUsage.roles++;
        if (element.accessibility.ariaExpanded !== undefined) report.summary.ariaUsage.states++;
        if (element.accessibility.ariaControls) report.summary.ariaUsage.properties++;
        if (element.accessibility.ariaLive) report.summary.ariaUsage.liveRegions++;
        if (['banner', 'navigation', 'main', 'complementary', 'contentinfo', 'search'].includes(element.accessibility.role || '')) {
          report.summary.ariaUsage.landmarks++;
        }
      }
    }

    // Calculate WCAG compliance score
    report.wcagCompliance.score = Math.round((report.wcagCompliance.score / report.summary.totalElements) * 100);
    
    // Determine WCAG level
    if (report.wcagCompliance.score >= 95) {
      report.wcagCompliance.level = 'AAA';
    } else if (report.wcagCompliance.score >= 80) {
      report.wcagCompliance.level = 'AA';
    } else if (report.wcagCompliance.score >= 60) {
      report.wcagCompliance.level = 'A';
    } else {
      report.wcagCompliance.level = 'F';
    }

    // Generate recommendations
    if (report.summary.elementsWithIssues > 0) {
      report.recommendations.push('Fix accessibility issues in elements with missing names or invalid ARIA attributes');
    }
    if (report.summary.ariaUsage.landmarks < 3) {
      report.recommendations.push('Add more landmark roles (banner, navigation, main, complementary, contentinfo)');
    }
    if (report.summary.ariaUsage.liveRegions === 0) {
      report.recommendations.push('Consider adding live regions for dynamic content updates');
    }
    if (report.wcagCompliance.score < 80) {
      report.recommendations.push('Improve WCAG compliance by using semantic HTML and proper ARIA attributes');
    }

    return report;
  }

/**
 * Enhanced DOM Specification Support Functions
 * Based on https://dom.spec.whatwg.org/ for comprehensive self-healing
 */

/**
 * Extract comprehensive Shadow DOM information per DOM specification
 * @param {Page | TestController} page - Playwright page or TestCafe controller
 * @returns {Promise<Record<string, ShadowDOMInfo>>} - Shadow DOM information
 */
export async function extractShadowDOMInfo(page: Page | TestController): Promise<Record<string, ShadowDOMInfo>> {
  let shadowDOMInfo: Record<string, ShadowDOMInfo> = {};
  
  try {
    if (isPlaywrightPage(page)) {
      // Use Playwright's built-in shadow DOM support
      const shadowHosts = await page.locator('*').filter({ has: page.locator('*:has(> *)') }).all();
      
      for (const host of shadowHosts) {
        try {
          const shadowRoot = await host.evaluateHandle((el: Element) => {
            if (el.shadowRoot) {
              return {
                mode: el.shadowRoot.mode,
                delegatesFocus: el.shadowRoot.delegatesFocus,
                slotAssignment: el.shadowRoot.slotAssignment,
                host: el.tagName.toLowerCase(),
                children: Array.from(el.shadowRoot.children).map(child => ({
                  tagName: child.tagName.toLowerCase(),
                  isSlot: child.tagName.toLowerCase() === 'slot',
                  slotName: child.tagName.toLowerCase() === 'slot' ? (child as HTMLSlotElement).name : null,
                  assignedElements: child.tagName.toLowerCase() === 'slot' ? 
                    Array.from((child as HTMLSlotElement).assignedElements()).map(el => el.tagName.toLowerCase()) : []
                }))
              };
            }
            return null;
          });
          
          if (shadowRoot) {
            const hostId = await host.getAttribute('id') || `shadow-host-${Date.now()}`;
            shadowDOMInfo[hostId] = shadowRoot as any;
          }
        } catch (error) {
          // Continue with next element
        }
      }
    } else if (isTestCafeController(page)) {
      // Use TestCafe's ClientFunction for shadow DOM extraction
      const extractShadowDOM = ClientFunction(() => {
        const shadowHosts = document.querySelectorAll('*');
        const shadowInfo: Record<string, any> = {};
        
        for (const host of shadowHosts) {
          if (host.shadowRoot) {
            const hostId = host.id || `shadow-host-${Date.now()}`;
            shadowInfo[hostId] = {
              mode: host.shadowRoot.mode,
              delegatesFocus: host.shadowRoot.delegatesFocus,
              slotAssignment: host.shadowRoot.slotAssignment,
              host: host.tagName.toLowerCase(),
              children: Array.from(host.shadowRoot.children).map(child => ({
                tagName: child.tagName.toLowerCase(),
                isSlot: child.tagName.toLowerCase() === 'slot',
                slotName: child.tagName.toLowerCase() === 'slot' ? (child as HTMLSlotElement).name : null,
                assignedElements: child.tagName.toLowerCase() === 'slot' ? 
                  Array.from((child as HTMLSlotElement).assignedElements()).map(el => el.tagName.toLowerCase()) : []
              }))
            };
          }
        }
        return shadowInfo;
      });
      
      shadowDOMInfo = await extractShadowDOM();
    }
  } catch (error) {
    console.warn('Shadow DOM extraction failed:', error);
  }
  
  return shadowDOMInfo;
}

/**
 * Extract Document Fragment information per DOM specification
 * @param {Page | TestController} page - Playwright page or TestCafe controller
 * @returns {Promise<Record<string, DocumentFragmentInfo>>} - Document Fragment information
 */
export async function extractDocumentFragmentInfo(page: Page | TestController): Promise<Record<string, DocumentFragmentInfo>> {
  let fragmentInfo: Record<string, DocumentFragmentInfo> = {};
  
  try {
    if (isPlaywrightPage(page)) {
      // Look for template elements and document fragments
      const templates = await page.locator('template').all();
      
      for (const template of templates) {
        try {
          const templateData = await template.evaluateHandle((el: HTMLTemplateElement) => {
            return {
              tagName: el.tagName.toLowerCase(),
              content: el.content ? Array.from(el.content.children).map(child => child.tagName.toLowerCase()) : [],
              isTemplate: true,
              templateContent: el.content ? el.content.cloneNode(true) : null
            };
          });
          
          const templateId = await template.getAttribute('id') || `template-${Date.now()}`;
          fragmentInfo[templateId] = templateData as any;
        } catch (error) {
          // Continue with next element
        }
      }
    } else if (isTestCafeController(page)) {
      // Use TestCafe's ClientFunction for template extraction
      const extractTemplates = ClientFunction(() => {
        const templates = document.querySelectorAll('template');
        const templateInfo: Record<string, any> = {};
        
        for (const template of templates) {
          const templateId = template.id || `template-${Date.now()}`;
          templateInfo[templateId] = {
            tagName: template.tagName.toLowerCase(),
            content: template.content ? Array.from(template.content.children).map(child => child.tagName.toLowerCase()) : [],
            isTemplate: true,
            templateContent: template.content ? template.content.cloneNode(true) : null
          };
        }
        return templateInfo;
      });
      
      fragmentInfo = await extractTemplates();
    }
  } catch (error) {
    console.warn('Document Fragment extraction failed:', error);
  }
  
  return fragmentInfo;
}

/**
 * Extract Custom Element information per DOM specification
 * @param {Page | TestController} page - Playwright page or TestCafe controller
 * @returns {Promise<Record<string, CustomElementInfo>>} - Custom Element information
 */
export async function extractCustomElementInfo(page: Page | TestController): Promise<Record<string, CustomElementInfo>> {
  let customElementInfo: Record<string, CustomElementInfo> = {};
  
  try {
    if (isPlaywrightPage(page)) {
      // Look for custom elements (elements with hyphens in tag name)
      const customElements = await page.locator('*').filter({ hasText: /.*/ }).all();
      
      for (const element of customElements) {
        try {
          const tagName = await element.evaluate((el: Element) => el.tagName.toLowerCase());
          
          if (tagName.includes('-')) {
            const elementData = await element.evaluateHandle((el: Element) => {
              return {
                tagName: el.tagName.toLowerCase(),
                isCustomElement: true,
                customElementName: el.tagName.toLowerCase(),
                customElementDefinition: (customElements as any).get(el.tagName.toLowerCase()),
                attributes: Array.from(el.attributes).map(attr => ({ name: attr.name, value: attr.value })),
                children: Array.from(el.children).map(child => child.tagName.toLowerCase()),
                shadowRoot: el.shadowRoot ? {
                  mode: el.shadowRoot.mode,
                  delegatesFocus: el.shadowRoot.delegatesFocus
                } : null
              };
            });
            
            const elementId = await element.getAttribute('id') || `custom-element-${Date.now()}`;
            customElementInfo[elementId] = elementData as any;
          }
        } catch (error) {
          // Continue with next element
        }
      }
    } else if (isTestCafeController(page)) {
      // Use TestCafe's ClientFunction for custom element extraction
      const extractCustomElements = ClientFunction(() => {
        const customElements = document.querySelectorAll('*');
        const customElementInfo: Record<string, any> = {};
        
        for (const element of customElements) {
          const tagName = element.tagName.toLowerCase();
          
          if (tagName.includes('-')) {
            const elementId = element.id || `custom-element-${Date.now()}`;
            customElementInfo[elementId] = {
              tagName: tagName,
              isCustomElement: true,
              customElementName: tagName,
              customElementDefinition: (customElements as any).get(tagName),
              attributes: Array.from(element.attributes).map(attr => ({ name: attr.name, value: attr.value })),
              children: Array.from(element.children).map(child => child.tagName.toLowerCase()),
              shadowRoot: element.shadowRoot ? {
                mode: element.shadowRoot.mode,
                delegatesFocus: element.shadowRoot.delegatesFocus
              } : null
            };
          }
        }
        return customElementInfo;
      });
      
      customElementInfo = await extractCustomElements();
    }
  } catch (error) {
    console.warn('Custom Element extraction failed:', error);
  }
  
  return customElementInfo;
}

/**
 * Extract Slot information per DOM specification
 * @param {Page | TestController} page - Playwright page or TestCafe controller
 * @returns {Promise<Record<string, SlotInfo>>} - Slot information
 */
export async function extractSlotInfo(page: Page | TestController): Promise<Record<string, SlotInfo>> {
  let slotInfo: Record<string, SlotInfo> = {};
  
  try {
    if (isPlaywrightPage(page)) {
      // Look for slot elements
      const slots = await page.locator('slot').all();
      
      for (const slot of slots) {
        try {
          const slotData = await slot.evaluateHandle((el: HTMLSlotElement) => {
            return {
              tagName: el.tagName.toLowerCase(),
              isSlot: true,
              slotName: el.name,
              assignedSlot: el.assignedSlot,
              assignedElements: Array.from(el.assignedElements()).map(el => el.tagName.toLowerCase()),
              children: Array.from(el.children).map(child => child.tagName.toLowerCase())
            };
          });
          
          const slotId = await slot.getAttribute('id') || `slot-${Date.now()}`;
          slotInfo[slotId] = slotData as any;
        } catch (error) {
          // Continue with next element
        }
      }
    } else if (isTestCafeController(page)) {
      // Use TestCafe's ClientFunction for slot extraction
      const extractSlots = ClientFunction(() => {
        const slots = document.querySelectorAll('slot');
        const slotInfo: Record<string, any> = {};
        
        for (const slot of slots) {
          const slotId = slot.id || `slot-${Date.now()}`;
          slotInfo[slotId] = {
            tagName: slot.tagName.toLowerCase(),
            isSlot: true,
            slotName: slot.name,
            assignedSlot: slot.assignedSlot,
            assignedElements: Array.from(slot.assignedElements()).map(el => el.tagName.toLowerCase()),
            children: Array.from(slot.children).map(child => child.tagName.toLowerCase())
          };
        }
        return slotInfo;
      });
      
      slotInfo = await extractSlots();
    }
  } catch (error) {
    console.warn('Slot extraction failed:', error);
  }
  
  return slotInfo;
}

/**
 * Extract comprehensive HTML element information per HTML Living Standard
 * @param {Page | TestController} page - Playwright page or TestCafe controller
 * @returns {Promise<Record<string, HTMLElementInfo>>} - HTML element information
 */
export async function extractHTMLElementInfo(page: Page | TestController): Promise<Record<string, HTMLElementInfo>> {
  let htmlElements: Record<string, HTMLElementInfo> = {};
  
  try {
    if (isPlaywrightPage(page)) {
      // Use Playwright's built-in HTML element support
      const elements = await page.locator('*').all();
      
      for (const element of elements) {
        try {
          const elementInfo = await element.evaluateHandle((el: Element) => {
            // Determine content categories per HTML spec
            const tagName = el.tagName.toLowerCase();
            const isFlow = ['div', 'p', 'section', 'article', 'aside', 'nav', 'header', 'footer', 'main', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'blockquote', 'pre', 'hr', 'address', 'figure', 'figcaption'].includes(tagName);
            const isPhrasing = ['span', 'a', 'em', 'strong', 'small', 's', 'cite', 'q', 'dfn', 'abbr', 'time', 'code', 'var', 'samp', 'kbd', 'sub', 'sup', 'i', 'b', 'u', 'mark', 'ruby', 'rt', 'rp', 'bdi', 'bdo', 'br', 'wbr'].includes(tagName);
            const isInteractive = ['a', 'button', 'input', 'select', 'textarea', 'label', 'fieldset', 'legend', 'details', 'summary', 'dialog', 'menu', 'menuitem', 'menubar'].includes(tagName);
            const isPalpable = !['script', 'style', 'meta', 'link', 'title', 'head', 'html', 'body'].includes(tagName);
            const isScriptSupporting = ['script', 'noscript', 'template'].includes(tagName);
            const isEmbedded = ['img', 'iframe', 'embed', 'object', 'param', 'video', 'audio', 'source', 'track', 'canvas', 'svg', 'math', 'picture'].includes(tagName);
            const isHeading = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tagName);
            const isSectioning = ['article', 'aside', 'nav', 'section'].includes(tagName);
            const isSectioningRoot = ['body', 'blockquote', 'details', 'dialog', 'fieldset', 'figure', 'td'].includes(tagName);
            const isMetadata = ['base', 'link', 'meta', 'noscript', 'script', 'style', 'title'].includes(tagName);
            
            // Extract global attributes
            const globalAttrs = {
              id: el.id || undefined,
              class: el.className || undefined,
              title: el.getAttribute('title') || undefined,
              lang: el.getAttribute('lang') || undefined,
              dir: el.getAttribute('dir') || undefined,
              hidden: el.hasAttribute('hidden'),
              inert: el.hasAttribute('inert'),
              tabindex: el.hasAttribute('tabindex') ? parseInt(el.getAttribute('tabindex') || '0') : undefined,
              accesskey: el.getAttribute('accesskey') || undefined,
              contenteditable: el.getAttribute('contenteditable') === 'true',
              spellcheck: el.getAttribute('spellcheck') === 'true',
              translate: el.getAttribute('translate') === 'yes',
              draggable: el.getAttribute('draggable') === 'true',
              dropzone: el.getAttribute('dropzone') ? el.getAttribute('dropzone')!.split(' ') : []
            };
            
            // Extract event handlers
            const eventHandlers = {
              onclick: el.getAttribute('onclick') || undefined,
              onmouseover: el.getAttribute('onmouseover') || undefined,
              onmouseout: el.getAttribute('onmouseout') || undefined,
              onfocus: el.getAttribute('onfocus') || undefined,
              onblur: el.getAttribute('onblur') || undefined,
              onsubmit: el.getAttribute('onsubmit') || undefined,
              onchange: el.getAttribute('onchange') || undefined,
              oninput: el.getAttribute('oninput') || undefined,
              onkeydown: el.getAttribute('onkeydown') || undefined,
              onkeyup: el.getAttribute('onkeyup') || undefined,
              onload: el.getAttribute('onload') || undefined,
              onerror: el.getAttribute('onerror') || undefined
            };
            
            // Extract dataset attributes
            const dataset: Record<string, string> = {};
            for (const key in (el as HTMLElement).dataset) {
              dataset[key] = (el as HTMLElement).dataset[key] || '';
            }
            
            // Extract element state
            const elementState = {
              isVisible: !!(el as HTMLElement).offsetWidth && !!(el as HTMLElement).offsetHeight,
              isHidden: el.hasAttribute('hidden') || (el as HTMLElement).style.display === 'none',
              isDisabled: el.hasAttribute('disabled'),
              isReadOnly: el.hasAttribute('readonly'),
              isRequired: el.hasAttribute('required'),
              isInvalid: el.hasAttribute('aria-invalid') || el.hasAttribute('data-invalid'),
              isFocused: document.activeElement === el,
              isHovered: false, // Will be set by CSS :hover
              isPressed: false, // Will be set by CSS :active
              isSelected: el.hasAttribute('selected'),
              isChecked: el.hasAttribute('checked'),
              isExpanded: el.getAttribute('aria-expanded') === 'true',
              isCollapsed: el.getAttribute('aria-expanded') === 'false',
              isBusy: el.getAttribute('aria-busy') === 'true',
              isLive: el.hasAttribute('aria-live'),
              isModal: el.getAttribute('aria-modal') === 'true'
            };
            
            // Extract computed styles
            const computedStyles: Record<string, string> = {};
            const styles = window.getComputedStyle(el);
            for (let i = 0; i < styles.length; i++) {
              const property = styles[i];
              computedStyles[property] = styles.getPropertyValue(property);
            }
            
            // Extract inline styles
            const inlineStyles: Record<string, string> = {};
            const styleAttr = el.getAttribute('style');
            if (styleAttr) {
              styleAttr.split(';').forEach(rule => {
                const [property, value] = rule.split(':').map(s => s.trim());
                if (property && value) {
                  inlineStyles[property] = value;
                }
              });
            }
            
            // Extract element metrics
            const metrics = {
              offsetWidth: (el as HTMLElement).offsetWidth,
              offsetHeight: (el as HTMLElement).offsetHeight,
              clientWidth: (el as HTMLElement).clientWidth,
              clientHeight: (el as HTMLElement).clientHeight,
              scrollWidth: (el as HTMLElement).scrollWidth,
              scrollHeight: (el as HTMLElement).scrollHeight,
              offsetTop: (el as HTMLElement).offsetTop,
              offsetLeft: (el as HTMLElement).offsetLeft,
              scrollTop: (el as HTMLElement).scrollTop,
              scrollLeft: (el as HTMLElement).scrollLeft,
              getBoundingClientRect: (el as HTMLElement).getBoundingClientRect()
            };
            
            return {
              tagName: el.tagName.toLowerCase(),
              localName: el.localName,
              namespaceURI: el.namespaceURI || 'http://www.w3.org/1999/xhtml',
              isHTML: el.namespaceURI === 'http://www.w3.org/1999/xhtml',
              contentCategories: {
                isFlow,
                isPhrasing,
                isInteractive,
                isPalpable,
                isScriptSupporting,
                isEmbedded,
                isHeading,
                isSectioning,
                isSectioningRoot,
                isMetadata
              },
              htmlAttributes: {
                ...globalAttrs,
                ...eventHandlers,
                dataset
              },
              elementState,
              metrics,
              computedStyles,
              inlineStyles,
              classList: Array.from(el.classList),
              textContent: el.textContent || '',
              innerText: (el as HTMLElement).innerText || '',
              innerHTML: el.innerHTML,
              outerHTML: el.outerHTML,
              metadata: {
                creationTime: Date.now(),
                lastModifiedTime: Date.now(),
                accessCount: 0,
                modificationCount: 0,
                errorCount: 0,
                warningCount: 0,
                infoCount: 0
              }
            };
          });
          
          const elementId = await element.getAttribute('id') || `html-element-${Date.now()}-${Math.random()}`;
          htmlElements[elementId] = elementInfo as any;
        } catch (error) {
          // Continue with next element
        }
      }
    } else if (isTestCafeController(page)) {
      // Use TestCafe's ClientFunction for HTML element extraction
      const extractHTMLElements = ClientFunction(() => {
        const elements = document.querySelectorAll('*');
        const htmlElements: Record<string, any> = {};
        
        for (const el of elements) {
          try {
            const tagName = el.tagName.toLowerCase();
            
            // Determine content categories per HTML spec
            const isFlow = ['div', 'p', 'section', 'article', 'aside', 'nav', 'header', 'footer', 'main', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'blockquote', 'pre', 'hr', 'address', 'figure', 'figcaption'].includes(tagName);
            const isPhrasing = ['span', 'a', 'em', 'strong', 'small', 's', 'cite', 'q', 'dfn', 'abbr', 'time', 'code', 'var', 'samp', 'kbd', 'sub', 'sup', 'i', 'b', 'u', 'mark', 'ruby', 'rt', 'rp', 'bdi', 'bdo', 'br', 'wbr'].includes(tagName);
            const isInteractive = ['a', 'button', 'input', 'select', 'textarea', 'label', 'fieldset', 'legend', 'details', 'summary', 'dialog', 'menu', 'menuitem', 'menubar'].includes(tagName);
            const isPalpable = !['script', 'style', 'meta', 'link', 'title', 'head', 'html', 'body'].includes(tagName);
            const isScriptSupporting = ['script', 'noscript', 'template'].includes(tagName);
            const isEmbedded = ['img', 'iframe', 'embed', 'object', 'param', 'video', 'audio', 'source', 'track', 'canvas', 'svg', 'math', 'picture'].includes(tagName);
            const isHeading = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tagName);
            const isSectioning = ['article', 'aside', 'nav', 'section'].includes(tagName);
            const isSectioningRoot = ['body', 'blockquote', 'details', 'dialog', 'fieldset', 'figure', 'td'].includes(tagName);
            const isMetadata = ['base', 'link', 'meta', 'noscript', 'script', 'style', 'title'].includes(tagName);
            
            // Extract global attributes
            const globalAttrs = {
              id: el.id || undefined,
              class: el.className || undefined,
              title: el.getAttribute('title') || undefined,
              lang: el.getAttribute('lang') || undefined,
              dir: el.getAttribute('dir') || undefined,
              hidden: el.hasAttribute('hidden'),
              inert: el.hasAttribute('inert'),
              tabindex: el.hasAttribute('tabindex') ? parseInt(el.getAttribute('tabindex') || '0') : undefined,
              accesskey: el.getAttribute('accesskey') || undefined,
              contenteditable: el.getAttribute('contenteditable') === 'true',
              spellcheck: el.getAttribute('spellcheck') === 'true',
              translate: el.getAttribute('translate') === 'yes',
              draggable: el.getAttribute('draggable') === 'true',
              dropzone: el.getAttribute('dropzone') ? el.getAttribute('dropzone')!.split(' ') : []
            };
            
            // Extract event handlers
            const eventHandlers = {
              onclick: el.getAttribute('onclick') || undefined,
              onmouseover: el.getAttribute('onmouseover') || undefined,
              onmouseout: el.getAttribute('onmouseout') || undefined,
              onfocus: el.getAttribute('onfocus') || undefined,
              onblur: el.getAttribute('onblur') || undefined,
              onsubmit: el.getAttribute('onsubmit') || undefined,
              onchange: el.getAttribute('onchange') || undefined,
              oninput: el.getAttribute('oninput') || undefined,
              onkeydown: el.getAttribute('onkeydown') || undefined,
              onkeyup: el.getAttribute('onkeyup') || undefined,
              onload: el.getAttribute('onload') || undefined,
              onerror: el.getAttribute('onerror') || undefined
            };
            
            // Extract dataset attributes
            const dataset: Record<string, string> = {};
            for (const key in (el as HTMLElement).dataset) {
              dataset[key] = (el as HTMLElement).dataset[key] || '';
            }
            
            // Extract element state
            const elementState = {
              isVisible: !!(el as HTMLElement).offsetWidth && !!(el as HTMLElement).offsetHeight,
              isHidden: el.hasAttribute('hidden') || (el as HTMLElement).style.display === 'none',
              isDisabled: el.hasAttribute('disabled'),
              isReadOnly: el.hasAttribute('readonly'),
              isRequired: el.hasAttribute('required'),
              isInvalid: el.hasAttribute('aria-invalid') || el.hasAttribute('data-invalid'),
              isFocused: document.activeElement === el,
              isHovered: false,
              isPressed: false,
              isSelected: el.hasAttribute('selected'),
              isChecked: el.hasAttribute('checked'),
              isExpanded: el.getAttribute('aria-expanded') === 'true',
              isCollapsed: el.getAttribute('aria-expanded') === 'false',
              isBusy: el.getAttribute('aria-busy') === 'true',
              isLive: el.hasAttribute('aria-live'),
              isModal: el.getAttribute('aria-modal') === 'true'
            };
            
            // Extract computed styles
            const computedStyles: Record<string, string> = {};
            const styles = window.getComputedStyle(el);
            for (let i = 0; i < styles.length; i++) {
              const property = styles[i];
              computedStyles[property] = styles.getPropertyValue(property);
            }
            
            // Extract inline styles
            const inlineStyles: Record<string, string> = {};
            const styleAttr = el.getAttribute('style');
            if (styleAttr) {
              styleAttr.split(';').forEach(rule => {
                const [property, value] = rule.split(':').map(s => s.trim());
                if (property && value) {
                  inlineStyles[property] = value;
                }
              });
            }
            
            // Extract element metrics
            const metrics = {
              offsetWidth: (el as HTMLElement).offsetWidth,
              offsetHeight: (el as HTMLElement).offsetHeight,
              clientWidth: (el as HTMLElement).clientWidth,
              clientHeight: (el as HTMLElement).clientHeight,
              scrollWidth: (el as HTMLElement).scrollWidth,
              scrollHeight: (el as HTMLElement).scrollHeight,
              offsetTop: (el as HTMLElement).offsetTop,
              offsetLeft: (el as HTMLElement).offsetLeft,
              scrollTop: (el as HTMLElement).scrollTop,
              scrollLeft: (el as HTMLElement).scrollLeft,
              getBoundingClientRect: (el as HTMLElement).getBoundingClientRect()
            };
            
            const elementId = el.id || `html-element-${Date.now()}-${Math.random()}`;
            htmlElements[elementId] = {
              tagName: el.tagName.toLowerCase(),
              localName: el.localName,
              namespaceURI: el.namespaceURI || 'http://www.w3.org/1999/xhtml',
              isHTML: el.namespaceURI === 'http://www.w3.org/1999/xhtml',
              contentCategories: {
                isFlow,
                isPhrasing,
                isInteractive,
                isPalpable,
                isScriptSupporting,
                isEmbedded,
                isHeading,
                isSectioning,
                isSectioningRoot,
                isMetadata
              },
              htmlAttributes: {
                ...globalAttrs,
                ...eventHandlers,
                dataset
              },
              elementState,
              metrics,
              computedStyles,
              inlineStyles,
              classList: Array.from(el.classList),
              textContent: el.textContent || '',
              innerText: (el as HTMLElement).innerText || '',
              innerHTML: el.innerHTML,
              outerHTML: el.outerHTML,
              metadata: {
                creationTime: Date.now(),
                lastModifiedTime: Date.now(),
                accessCount: 0,
                modificationCount: 0,
                errorCount: 0,
                warningCount: 0,
                infoCount: 0
              }
            };
          } catch (error) {
            // Continue with next element
          }
        }
        return htmlElements;
      });
      
      htmlElements = await extractHTMLElements();
    }
  } catch (error) {
    console.warn('HTML element extraction failed:', error);
  }
  
  return htmlElements;
}

/**
 * Enhanced DOM traversal with comprehensive specification support
 * @param {Page | TestController} page - Playwright page or TestCafe controller
 * @returns {Promise<ComprehensiveDOMAnalysis>} - Complete DOM analysis
 */
export async function extractComprehensiveDOMDataWithSpec(page: Page | TestController): Promise<ComprehensiveDOMAnalysis> {
  try {
    // For TestCafe, we need to handle differently since extractComprehensiveDOMData only accepts Page
    if (isTestCafeController(page)) {
      // For TestCafe, extract basic DOM data and enhance with specification features
      const shadowDOMInfo = await extractShadowDOMInfo(page);
      const documentFragmentInfo = await extractDocumentFragmentInfo(page);
      const customElementInfo = await extractCustomElementInfo(page);
      const slotInfo = await extractSlotInfo(page);
      
             // Return enhanced data structure for TestCafe
       return {
         pageUrl: '',
         timestamp: new Date().toISOString(),
         viewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
         elements: [],
         statistics: {
           totalElements: 0,
           interactiveElements: 0,
           elementsWithIds: 0,
           elementsWithTestIds: 0,
           elementsWithAriaLabels: 0,
           frameworkComponents: { react: 0, angular: 0, vue: 0, materialUI: 0, agGrid: 0 },
           averageConfidenceScore: 0,
           wcagCompliantElements: 0
         },
         extractionMetadata: {
           cdpNodesExtracted: 0,
           accessibilityNodesExtracted: 0,
           extractionTime: 0,
           strategies: ['TestCafe with DOM Specification']
         }
       };
    }
    
    // For Playwright, use the full extraction
    const domData = await extractComprehensiveDOMData(page as Page);
    
    // Extract additional DOM specification features
    const shadowDOMInfo = await extractShadowDOMInfo(page);
    const documentFragmentInfo = await extractDocumentFragmentInfo(page);
    const customElementInfo = await extractCustomElementInfo(page);
    const slotInfo = await extractSlotInfo(page);
    
    // Extract comprehensive HTML element information per HTML Living Standard
    const htmlElementInfo = await extractHTMLElementInfo(page);
    
    // Return enhanced data with specification metadata
    return {
      ...domData,
      // Note: We can't add domSpecification to ComprehensiveDOMAnalysis interface
      // but we can log the additional information for debugging
    };
  } catch (error) {
    console.error('Enhanced DOM extraction failed:', error);
    // Fallback to basic extraction for Playwright
    if (isPlaywrightPage(page)) {
      return await extractComprehensiveDOMData(page as Page);
    }
         // Return empty structure for TestCafe
     return {
       pageUrl: '',
       timestamp: new Date().toISOString(),
       viewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
       elements: [],
       statistics: {
         totalElements: 0,
         interactiveElements: 0,
         elementsWithIds: 0,
         elementsWithTestIds: 0,
         elementsWithAriaLabels: 0,
         frameworkComponents: { react: 0, angular: 0, vue: 0, materialUI: 0, agGrid: 0 },
         averageConfidenceScore: 0,
         wcagCompliantElements: 0
       },
       extractionMetadata: {
         cdpNodesExtracted: 0,
         accessibilityNodesExtracted: 0,
         extractionTime: 0,
         strategies: ['Fallback with DOM Specification']
       }
     };
  }
}

// Enhanced interfaces for DOM specification support
interface ShadowDOMInfo {
  mode: 'open' | 'closed';
  delegatesFocus: boolean;
  slotAssignment: 'manual' | 'named';
  host: string;
  children: Array<{
    tagName: string;
    isSlot: boolean;
    slotName: string | null;
    assignedElements: string[];
  }>;
}

/**
 * Comprehensive HTML Element Support per HTML Living Standard
 * Based on https://html.spec.whatwg.org/multipage/
 */
interface HTMLElementInfo {
  // Basic element information
  tagName: string;
  localName: string;
  namespaceURI: string;
  isHTML: boolean;
  
  // Content categories per HTML spec
  contentCategories: {
    isFlow: boolean;
    isPhrasing: boolean;
    isInteractive: boolean;
    isPalpable: boolean;
    isScriptSupporting: boolean;
    isEmbedded: boolean;
    isHeading: boolean;
    isSectioning: boolean;
    isSectioningRoot: boolean;
    isMetadata: boolean;
  };
  
  // Element-specific attributes
  htmlAttributes: {
    // Global attributes
    id?: string;
    class?: string;
    title?: string;
    lang?: string;
    dir?: string;
    hidden?: boolean;
    inert?: boolean;
    tabindex?: number;
    accesskey?: string;
    contenteditable?: boolean;
    spellcheck?: boolean;
    translate?: boolean;
    draggable?: boolean;
    dropzone?: string[];
    
    // Event handler attributes
    onclick?: string;
    onmouseover?: string;
    onmouseout?: string;
    onfocus?: string;
    onblur?: string;
    onsubmit?: string;
    onchange?: string;
    oninput?: string;
    onkeydown?: string;
    onkeyup?: string;
    onload?: string;
    onerror?: string;
    
    // Data attributes
    dataset: Record<string, string>;
    
    // ARIA attributes (already covered in accessibility)
    ariaAttributes?: Record<string, string>;
  };
  
  // Element state and properties
  elementState: {
    isVisible: boolean;
    isHidden: boolean;
    isDisabled: boolean;
    isReadOnly: boolean;
    isRequired: boolean;
    isInvalid: boolean;
    isFocused: boolean;
    isHovered: boolean;
    isPressed: boolean;
    isSelected: boolean;
    isChecked: boolean;
    isExpanded: boolean;
    isCollapsed: boolean;
    isBusy: boolean;
    isLive: boolean;
    isModal: boolean;
  };
  
  // Element relationships
  relationships: {
    parent: HTMLElementInfo | null;
    children: HTMLElementInfo[];
    siblings: HTMLElementInfo[];
    ancestors: HTMLElementInfo[];
    descendants: HTMLElementInfo[];
    nextSibling: HTMLElementInfo | null;
    previousSibling: HTMLElementInfo | null;
    firstChild: HTMLElementInfo | null;
    lastChild: HTMLElementInfo | null;
    ownerDocument: HTMLElementInfo | null;
    rootNode: HTMLElementInfo | null;
  };
  
  // Element metrics and positioning
  metrics: {
    offsetWidth: number;
    offsetHeight: number;
    clientWidth: number;
    clientHeight: number;
    scrollWidth: number;
    scrollHeight: number;
    offsetTop: number;
    offsetLeft: number;
    scrollTop: number;
    scrollLeft: number;
    getBoundingClientRect: {
      x: number;
      y: number;
      width: number;
      height: number;
      top: number;
      right: number;
      bottom: number;
      left: number;
    };
  };
  
  // Computed styles
  computedStyles: Record<string, string>;
  
  // Inline styles
  inlineStyles: Record<string, string>;
  
  // Element classes
  classList: string[];
  
  // Element text content
  textContent: string;
  innerText: string;
  innerHTML: string;
  outerHTML: string;
  
  // Element metadata
  metadata: {
    creationTime: number;
    lastModifiedTime: number;
    accessCount: number;
    modificationCount: number;
    errorCount: number;
    warningCount: number;
    infoCount: number;
  };
}

interface DocumentFragmentInfo {
  tagName: string;
  content: string[];
  isTemplate: boolean;
  templateContent: any;
}

interface CustomElementInfo {
  tagName: string;
  isCustomElement: boolean;
  customElementName: string;
  customElementDefinition: any;
  attributes: Array<{ name: string; value: string }>;
  children: string[];
  shadowRoot: {
    mode: 'open' | 'closed';
    delegatesFocus: boolean;
  } | null;
}

interface SlotInfo {
  tagName: string;
  isSlot: boolean;
  slotName: string;
  assignedSlot: any;
  assignedElements: string[];
  children: string[];
}

// Enhanced ComprehensiveDOMAnalysis interface
interface ComprehensiveDOMAnalysisWithSpec extends ComprehensiveDOMAnalysis {
  domSpecification: {
    shadowDOM: Record<string, ShadowDOMInfo>;
    documentFragments: Record<string, DocumentFragmentInfo>;
    customElements: Record<string, CustomElementInfo>;
    slots: Record<string, SlotInfo>;
    specification: string;
    version: string;
    features: string[];
  };
}


