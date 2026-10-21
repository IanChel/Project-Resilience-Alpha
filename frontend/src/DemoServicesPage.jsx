import React from 'react';
import Icon from './icons.jsx';
import {Card,Badge,Alert} from './ui.jsx';
// Placeholders that describe the fictitious company around the payment service. They are deliberately inert:
// no status, no metric, no incident. Showing "opérationnel" here would be a fabricated observation.
const SERVICES=[
  {key:'crm',icon:'demo',name:'CRM clients',
   role:'Fiches des clients fictifs et historique commercial. Dans l’entreprise simulée, c’est la source des coordonnées de facturation utilisées par le service de paiement.',
   scope:'Hors périmètre de la démonstration de résilience.'},
  {key:'inventory',icon:'ledger',name:'Inventaire',
   role:'Catalogue et niveaux de stock fictifs. Un paiement confirmé déclencherait, dans une architecture complète, une réservation de stock.',
   scope:'Aucune intégration avec l’API paiement de ce laboratoire.'},
  {key:'notifications',icon:'alert',name:'Notifications',
   role:'Messages transactionnels (confirmation de paiement, alerte d’incident) vers les clients fictifs. Le code de vérification de connexion est, lui, bien réel.',
   scope:'Non relié : aucune notification n’est émise par cet écran.'},
];
export default function DemoServicesPage(){
  return <div className="space-y-5">
    <Alert tone="warn">
      Ces écrans sont des <strong>services fictifs de démonstration</strong>. Ils situent le service de paiement dans
      une entreprise simulée, mais ne sont reliés à aucun service réel : aucun état, aucune métrique et aucun
      incident n’est mesuré ici. Les données observées se trouvent dans Vue d’ensemble, Service paiement et Supervision.
    </Alert>
    <div className="grid gap-4 lg:grid-cols-3">{SERVICES.map(service=>
      <Card key={service.key} label={`Service fictif : ${service.name}`} className="flex flex-col">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 rounded-lg border border-slate-700 bg-slate-950 p-2 text-slate-400">
              <Icon name={service.icon}/></span>
            <h2 className="card-title pt-1.5">{service.name}</h2>
          </div>
          <Badge tone="warn">Fictif</Badge>
        </div>
        <p className="mt-3 text-sm text-slate-300">{service.role}</p>
        <p className="meta mt-auto border-t border-slate-800 pt-3">{service.scope}</p>
        <p className="meta mt-1">État : non mesuré.</p>
      </Card>)}
    </div>
    <Card title="Pourquoi ces écrans existent" hint="Périmètre de l’exercice">
      <p className="text-sm text-slate-300">
        Le sujet porte sur la reprise autonome du <strong>service de paiement</strong>. Les services ci-dessus
        rappellent qu’un paiement ne vit jamais seul dans une entreprise, sans pour autant élargir le périmètre
        instrumenté : seuls le paiement, le détecteur et le remédiateur sont réellement observés, mesurés et éprouvés
        par la recette.
      </p>
    </Card>
  </div>;
}
